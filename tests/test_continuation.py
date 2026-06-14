"""Tests for truncation detection, max_tokens clamp, thinking-disable and auto-continuation."""
import json

import pytest

from app.services import llm_service
from app.services.llm_service import (
    _build_request,
    _max_tokens,
    _response_truncated,
    call_llm_api_full,
    get_provider_info,
    stream_llm_api,
)


class TestResponseTruncated:
    def test_openai_finish_length(self):
        assert _response_truncated({'choices': [{'finish_reason': 'length'}]}, 'openai') is True

    def test_openai_finish_stop(self):
        assert _response_truncated({'choices': [{'finish_reason': 'stop'}]}, 'openai') is False

    def test_anthropic_max_tokens(self):
        assert _response_truncated({'stop_reason': 'max_tokens'}, 'anthropic') is True

    def test_anthropic_end_turn(self):
        assert _response_truncated({'stop_reason': 'end_turn'}, 'anthropic') is False

    def test_empty_payload(self):
        assert _response_truncated({}, 'openai') is False
        assert _response_truncated({}, 'anthropic') is False


class TestMaxTokensClamp:
    # monkeypatch.setitem : la fixture `app` est scope='session', il faut
    # restaurer LLM_MAX_TOKENS apres chaque test pour ne pas polluer les autres.
    def test_clamp_to_provider_cap(self, app, monkeypatch):
        monkeypatch.setitem(app.config, 'LLM_MAX_TOKENS', 100000)
        with app.app_context():
            assert _max_tokens('zai') == llm_service._PROVIDER_OUTPUT_CAP['zai']

    def test_no_cap_returns_config(self, app, monkeypatch):
        monkeypatch.setitem(app.config, 'LLM_MAX_TOKENS', 12000)
        with app.app_context():
            assert _max_tokens('openrouter') == 12000  # cap None

    def test_below_cap_unchanged(self, app, monkeypatch):
        monkeypatch.setitem(app.config, 'LLM_MAX_TOKENS', 8000)
        with app.app_context():
            assert _max_tokens('zai') == 8000

    def test_unknown_provider_no_clamp(self, app, monkeypatch):
        monkeypatch.setitem(app.config, 'LLM_MAX_TOKENS', 50000)
        with app.app_context():
            assert _max_tokens('inconnu') == 50000


class TestAnthropicThinkingDisabled:
    def test_opencode_anthropic_payload_disables_thinking(self, app):
        with app.app_context():
            provider = get_provider_info('opencode')
            _, _, payload, fmt = _build_request(
                provider, 'opencode', 'minimax-m3', 'sk', 'prompt', stream=True
            )
            assert fmt == 'anthropic'
            assert payload.get('thinking') == {'type': 'disabled'}

    def test_opencode_openai_branch_has_no_thinking(self, app):
        with app.app_context():
            provider = get_provider_info('opencode')
            _, _, payload, fmt = _build_request(
                provider, 'opencode', 'glm-5.1', 'sk', 'prompt', stream=False
            )
            assert fmt == 'openai'
            # opencode n'est pas dans _PROVIDER_PARAMS : pas de thinking ajoute
            assert 'thinking' not in payload

    def test_messages_override_used(self, app):
        with app.app_context():
            provider = get_provider_info('zai')
            msgs = [{'role': 'user', 'content': 'a'},
                    {'role': 'assistant', 'content': 'b'},
                    {'role': 'user', 'content': 'continue'}]
            _, _, payload, _ = _build_request(
                provider, 'zai', 'glm-5.1', 'sk', '', stream=False, messages=msgs
            )
            assert payload['messages'] == msgs


class _SyncResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class TestSyncAutoContinuation:
    def test_continues_until_complete(self, app, monkeypatch):
        seq = [
            {'choices': [{'message': {'content': 'Partie1 '}, 'finish_reason': 'length'}]},
            {'choices': [{'message': {'content': 'Partie2'}, 'finish_reason': 'stop'}]},
        ]
        calls = {'i': 0}

        def fake_post(*a, **k):
            r = _SyncResponse(seq[calls['i']])
            calls['i'] += 1
            return r

        monkeypatch.setattr(llm_service.http_requests, 'post', fake_post)
        with app.app_context():
            result, truncated, error, status = call_llm_api_full('p', 'zai', 'glm-5.1', 'sk')
        assert error is None
        assert result == 'Partie1 Partie2'
        assert truncated is False
        assert calls['i'] == 2

    def test_stops_at_max_continuations(self, app, monkeypatch):
        resp = {'choices': [{'message': {'content': 'x'}, 'finish_reason': 'length'}]}
        monkeypatch.setattr(llm_service.http_requests, 'post',
                            lambda *a, **k: _SyncResponse(resp))
        with app.app_context():
            result, truncated, error, status = call_llm_api_full('p', 'zai', 'glm-5.1', 'sk')
        assert error is None
        assert truncated is True
        assert result == 'x' * (llm_service.MAX_CONTINUATIONS + 1)

    def test_empty_truncated_does_not_loop(self, app, monkeypatch):
        # contenu vide + finish_reason length (budget mange par le thinking) : pas de boucle
        resp = {'choices': [{'message': {'content': ''}, 'finish_reason': 'length'}]}
        calls = {'i': 0}

        def fake_post(*a, **k):
            calls['i'] += 1
            return _SyncResponse(resp)

        monkeypatch.setattr(llm_service.http_requests, 'post', fake_post)
        with app.app_context():
            result, truncated, error, status = call_llm_api_full('p', 'zai', 'glm-5.1', 'sk')
        assert result is None
        assert 'vide' in error.lower()
        assert calls['i'] == 1


class _StreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for line in self._lines:
            yield line.encode('utf-8')


def _collect(generator):
    events = []
    for sse in generator:
        for line in sse.strip().split('\n'):
            if line.startswith('data: '):
                events.append(json.loads(line[6:]))
    return events


class TestStreamAutoContinuation:
    def test_stream_continues_and_concatenates(self, app, monkeypatch):
        turn1 = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'Debut '}}]}),
            'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'length'}]}),
            'data: [DONE]',
        ]
        turn2 = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'fin'}}]}),
            'data: [DONE]',
        ]
        seq = [turn1, turn2]
        calls = {'i': 0}

        def fake_post(*a, **k):
            r = _StreamResponse(seq[calls['i']])
            calls['i'] += 1
            return r

        monkeypatch.setattr(llm_service.http_requests, 'post', fake_post)
        with app.app_context():
            events = _collect(stream_llm_api('p', 'zai', 'glm-5.1', 'sk'))

        types = [e['type'] for e in events]
        assert 'continuing' in types
        done = events[-1]
        assert done['type'] == 'done'
        assert done['content'] == 'Debut fin'
        assert done['truncated'] is False
        assert calls['i'] == 2

    def test_continue_from_prepends_base(self, app, monkeypatch):
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'suite'}}]}),
            'data: [DONE]',
        ]
        captured = {}

        def fake_post(url, headers=None, json=None, stream=False, timeout=None):
            captured['payload'] = json
            return _StreamResponse(lines)

        monkeypatch.setattr(llm_service.http_requests, 'post', fake_post)
        with app.app_context():
            events = _collect(stream_llm_api('p', 'zai', 'glm-5.1', 'sk', continue_from='DEBUT '))

        done = events[-1]
        assert done['type'] == 'done'
        assert done['content'] == 'DEBUT suite'  # base + nouveau texte
        # le contexte de reprise est bien envoye au provider
        msgs = captured['payload']['messages']
        assert msgs[1] == {'role': 'assistant', 'content': 'DEBUT '}

    def test_stream_completes_in_one_turn(self, app, monkeypatch):
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'Complet'}}]}),
            'data: [DONE]',
        ]
        monkeypatch.setattr(llm_service.http_requests, 'post',
                            lambda *a, **k: _StreamResponse(lines))
        with app.app_context():
            events = _collect(stream_llm_api('p', 'zai', 'glm-5.1', 'sk'))
        assert 'continuing' not in [e['type'] for e in events]
        assert events[-1]['type'] == 'done'
        assert events[-1]['content'] == 'Complet'
        assert events[-1]['truncated'] is False
