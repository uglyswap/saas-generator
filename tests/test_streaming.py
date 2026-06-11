"""Tests for streaming parsing: thinking separation, truncation, upstream errors."""
import json

import pytest
import requests as http_requests_lib

from app.services.llm_service import (
    _extract_content,
    _http_error_details,
    _parse_stream_chunk,
    _stream_error,
    call_llm_api,
    stream_llm_api,
)


class TestParseStreamChunkOpenAI:
    """Format OpenAI (chat/completions) : GLM, Kimi, DeepSeek, MiMo..."""

    def test_content_token(self):
        chunk = {'choices': [{'delta': {'content': 'Bonjour'}}]}
        parsed = _parse_stream_chunk(chunk, 'openai')
        assert parsed['token'] == 'Bonjour'
        assert parsed['thinking'] == ''
        assert parsed['truncated'] is False

    def test_reasoning_content_separated_from_response(self):
        """Le thinking ne doit JAMAIS etre melange a la reponse."""
        chunk = {'choices': [{'delta': {'reasoning_content': 'je reflechis...'}}]}
        parsed = _parse_stream_chunk(chunk, 'openai')
        assert parsed['token'] == ''
        assert parsed['thinking'] == 'je reflechis...'

    def test_reasoning_field_openrouter(self):
        chunk = {'choices': [{'delta': {'reasoning': 'hmm'}}]}
        parsed = _parse_stream_chunk(chunk, 'openai')
        assert parsed['token'] == ''
        assert parsed['thinking'] == 'hmm'

    def test_simultaneous_content_and_reasoning(self):
        chunk = {'choices': [{'delta': {'content': 'reponse', 'reasoning_content': 'pensee'}}]}
        parsed = _parse_stream_chunk(chunk, 'openai')
        assert parsed['token'] == 'reponse'
        assert parsed['thinking'] == 'pensee'

    def test_finish_reason_length_marks_truncated(self):
        chunk = {'choices': [{'delta': {}, 'finish_reason': 'length'}]}
        assert _parse_stream_chunk(chunk, 'openai')['truncated'] is True

    def test_finish_reason_stop_not_truncated(self):
        chunk = {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}
        assert _parse_stream_chunk(chunk, 'openai')['truncated'] is False

    def test_empty_choices_no_crash(self):
        assert _parse_stream_chunk({'choices': []}, 'openai')['token'] == ''
        assert _parse_stream_chunk({}, 'openai')['token'] == ''


class TestParseStreamChunkAnthropic:
    """Format Anthropic (/messages) : MiniMax et Qwen via OpenCode Go."""

    def test_text_delta(self):
        chunk = {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'Salut'}}
        parsed = _parse_stream_chunk(chunk, 'anthropic')
        assert parsed['token'] == 'Salut'
        assert parsed['thinking'] == ''

    def test_thinking_delta_separated(self):
        chunk = {'type': 'content_block_delta', 'delta': {'type': 'thinking_delta', 'thinking': 'raisonnement'}}
        parsed = _parse_stream_chunk(chunk, 'anthropic')
        assert parsed['token'] == ''
        assert parsed['thinking'] == 'raisonnement'

    def test_message_stop(self):
        assert _parse_stream_chunk({'type': 'message_stop'}, 'anthropic')['stop'] is True

    def test_max_tokens_stop_reason_marks_truncated(self):
        chunk = {'type': 'message_delta', 'delta': {'stop_reason': 'max_tokens'}}
        assert _parse_stream_chunk(chunk, 'anthropic')['truncated'] is True

    def test_end_turn_not_truncated(self):
        chunk = {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}}
        assert _parse_stream_chunk(chunk, 'anthropic')['truncated'] is False

    def test_signature_delta_ignored(self):
        chunk = {'type': 'content_block_delta', 'delta': {'type': 'signature_delta', 'signature': 'xyz'}}
        parsed = _parse_stream_chunk(chunk, 'anthropic')
        assert parsed['token'] == ''
        assert parsed['thinking'] == ''


class TestStreamError:
    def test_anthropic_error_event(self):
        chunk = {'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'Overloaded'}}
        assert 'Overloaded' in _stream_error(chunk, 'anthropic')

    def test_openai_error_field(self):
        chunk = {'error': {'message': 'quota exceeded'}}
        assert 'quota exceeded' in _stream_error(chunk, 'openai')

    def test_no_error(self):
        assert _stream_error({'choices': [{'delta': {'content': 'x'}}]}, 'openai') is None
        assert _stream_error({'type': 'content_block_delta'}, 'anthropic') is None


class _FakeResponse:
    """Simule une reponse requests streamee."""

    def __init__(self, lines, raise_after=None):
        self._lines = lines
        self._raise_after = raise_after

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for line in self._lines:
            yield line.encode('utf-8')
        if self._raise_after is not None:
            raise self._raise_after


def _events(generator):
    """Collecte les events SSE emis par stream_llm_api."""
    events = []
    for sse in generator:
        for line in sse.strip().split('\n'):
            if line.startswith('data: '):
                events.append(json.loads(line[6:]))
    return events


class TestStreamLlmApi:
    """Integration du stream complet avec un provider simule."""

    def _run(self, app, monkeypatch, lines, provider='opencode', model='glm-5.1',
             raise_after=None):
        from app.services import llm_service

        def fake_post(url, headers=None, json=None, stream=False, timeout=None):
            return _FakeResponse(lines, raise_after=raise_after)

        monkeypatch.setattr(llm_service.http_requests, 'post', fake_post)
        with app.app_context():
            return _events(stream_llm_api('prompt', provider, model, 'sk-test'))

    def test_thinking_then_content_openai(self, app, monkeypatch):
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'reasoning_content': 'pense '}}]}),
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'Reponse'}}]}),
            'data: [DONE]',
        ]
        events = self._run(app, monkeypatch, lines)
        types = [e['type'] for e in events]
        assert types == ['start', 'thinking', 'token', 'done']
        done = events[-1]
        # Le thinking n'est pas dans le contenu final (donc pas dans l'historique)
        assert done['content'] == 'Reponse'
        assert done['truncated'] is False

    def test_truncated_flag_propagated(self, app, monkeypatch):
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'Coupe'}}]}),
            'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'length'}]}),
            'data: [DONE]',
        ]
        events = self._run(app, monkeypatch, lines)
        assert events[-1]['type'] == 'done'
        assert events[-1]['truncated'] is True

    def test_anthropic_stream_with_thinking(self, app, monkeypatch):
        lines = [
            'event: content_block_delta',
            'data: ' + json.dumps({'type': 'content_block_delta',
                                   'delta': {'type': 'thinking_delta', 'thinking': 'hmm'}}),
            'data: ' + json.dumps({'type': 'content_block_delta',
                                   'delta': {'type': 'text_delta', 'text': 'Voila'}}),
            'data: ' + json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}}),
            'data: ' + json.dumps({'type': 'message_stop'}),
        ]
        events = self._run(app, monkeypatch, lines, model='minimax-m3')
        types = [e['type'] for e in events]
        assert types == ['start', 'thinking', 'token', 'done']
        assert events[-1]['content'] == 'Voila'

    def test_upstream_error_stops_stream(self, app, monkeypatch):
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'partiel'}}]}),
            'data: ' + json.dumps({'error': {'message': 'backend exploded'}}),
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'jamais vu'}}]}),
        ]
        events = self._run(app, monkeypatch, lines)
        assert events[-1]['type'] == 'error'
        assert 'backend exploded' in events[-1]['message']
        # Aucun 'done' : le client ne doit pas croire a un succes
        assert all(e['type'] != 'done' for e in events)

    def test_sse_data_without_space_accepted(self, app, monkeypatch):
        """Certains providers emettent 'data:{...}' sans espace : valide en SSE."""
        lines = [
            'data:' + json.dumps({'choices': [{'delta': {'content': 'Compact'}}]}),
            'data:[DONE]',
        ]
        events = self._run(app, monkeypatch, lines)
        assert events[-1]['type'] == 'done'
        assert events[-1]['content'] == 'Compact'

    def test_reasoning_only_yields_error_not_empty_done(self, app, monkeypatch):
        """Reponse 100% raisonnement : erreur explicite, pas de faux succes vide."""
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'reasoning_content': 'je pense'}}]}),
            'data: [DONE]',
        ]
        events = self._run(app, monkeypatch, lines)
        assert all(e['type'] != 'done' for e in events)
        assert events[-1]['type'] == 'error'
        assert 'raisonnement' in events[-1]['message']

    def test_thinking_consumed_all_budget_yields_error(self, app, monkeypatch):
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'reasoning_content': 'pense...'}}]}),
            'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'length'}]}),
            'data: [DONE]',
        ]
        events = self._run(app, monkeypatch, lines)
        assert events[-1]['type'] == 'error'
        assert 'LLM_MAX_TOKENS' in events[-1]['message']

    def test_read_timeout_mid_stream_friendly_message(self, app, monkeypatch):
        """requests leve ConnectionError (pas Timeout) pendant iter_lines."""
        exc = http_requests_lib.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='opencode.ai', port=443): Read timed out. (read timeout=300)"
        )
        lines = ['data: ' + json.dumps({'choices': [{'delta': {'content': 'debut'}}]})]
        events = self._run(app, monkeypatch, lines, raise_after=exc)
        assert events[-1]['type'] == 'error'
        assert "Delai d'attente depasse" in events[-1]['message']
        assert 'HTTPSConnectionPool' not in events[-1]['message']

    def test_chunked_encoding_error_friendly_message(self, app, monkeypatch):
        exc = http_requests_lib.exceptions.ChunkedEncodingError('Connection broken')
        events = self._run(app, monkeypatch, [], raise_after=exc)
        assert events[-1]['type'] == 'error'
        assert 'interrompu' in events[-1]['message']
        assert 'Connection broken' not in events[-1]['message']

    def test_unexpected_exception_not_leaked(self, app, monkeypatch):
        exc = RuntimeError('secret interne sk-12345')
        events = self._run(app, monkeypatch, [], raise_after=exc)
        assert events[-1]['type'] == 'error'
        assert 'sk-12345' not in events[-1]['message']


class TestSyncReasoningPolicy:
    """Le chemin synchrone applique la meme politique que le stream."""

    def test_extract_content_does_not_fallback_to_reasoning(self):
        data = {'choices': [{'message': {'content': '', 'reasoning_content': 'pensee secrete'}}]}
        assert _extract_content(data, 'openai') == ''

    def test_sync_reasoning_only_returns_explicit_error(self, app, monkeypatch):
        from app.services import llm_service

        class _FakeSyncResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'choices': [{'message': {'reasoning_content': 'que du thinking'}}]}

        monkeypatch.setattr(llm_service.http_requests, 'post',
                            lambda *a, **k: _FakeSyncResponse())
        with app.app_context():
            result, error, status = call_llm_api('prompt', 'opencode', 'glm-5.1', 'sk-test')
        assert result is None
        assert 'vide' in error.lower()
        assert status == 502


class TestHttpErrorDetails:
    def _http_error(self, status, body):
        resp = http_requests_lib.Response()
        resp.status_code = status
        resp._content = json.dumps(body).encode('utf-8')
        return http_requests_lib.exceptions.HTTPError(response=resp)

    def test_400_body_message_surfaced(self):
        exc = self._http_error(400, {'error': {'message': 'max_tokens too large for this model'}})
        message, status = _http_error_details(exc)
        assert 'max_tokens too large' in message
        assert 'LLM_MAX_TOKENS' in message
        assert status == 502

    def test_401_no_body_leak(self):
        exc = self._http_error(401, {'error': {'message': 'bad key'}})
        message, status = _http_error_details(exc)
        assert status == 400
        assert 'Cle API invalide' in message
