"""Tests for the general default provider/model resolution and provider catalog."""
import json

import pytest

from app.models import ProviderConfig, Template, User
from app.utils.security import encrypt_api_key


def _setup_provider(db, user_id, provider_id, model_id):
    """Give a user an API key and a selected model for a provider."""
    pc = ProviderConfig(
        user_id=user_id,
        provider_id=provider_id,
        api_key_encrypted=encrypt_api_key('test-api-key'),
        selected_model=model_id,
    )
    db.session.add(pc)
    db.session.commit()
    return pc


def _create_template(auth_client, **extra):
    payload = {'name': 'Tpl', 'content': 'Bonjour {nom}'}
    payload.update(extra)
    resp = auth_client.post('/api/v1/templates',
                            data=json.dumps(payload),
                            content_type='application/json')
    assert resp.status_code == 201
    return resp.get_json()['template']


@pytest.fixture
def llm_spy(monkeypatch):
    """Capture call_llm_api arguments without any HTTP call."""
    calls = []

    def fake_call(prompt, provider_id, model_id, api_key):
        calls.append({'provider': provider_id, 'model': model_id})
        return 'Resultat genere', None, 200

    import app.api_v1 as api_v1
    monkeypatch.setattr(api_v1, 'call_llm_api', fake_call)
    return calls


class TestTemplateOverrideOptional:
    """A template without explicit choice must NOT pin a provider/model."""

    def test_create_without_override_stores_none(self, app, db, auth_client):
        tpl = _create_template(auth_client)
        assert tpl['default_provider'] == ''
        assert tpl['default_model'] == ''
        with app.app_context():
            row = db.session.get(Template, tpl['id'])
            assert row.default_provider is None
            assert row.default_model is None

    def test_create_with_override_keeps_it(self, auth_client):
        tpl = _create_template(auth_client, default_provider='alibaba',
                               default_model='qwen3.7-plus')
        assert tpl['default_provider'] == 'alibaba'
        assert tpl['default_model'] == 'qwen3.7-plus'

    def test_create_with_invalid_provider_rejected(self, auth_client):
        resp = auth_client.post('/api/v1/templates',
                                data=json.dumps({'name': 'X', 'content': 'y',
                                                 'default_provider': 'nope'}),
                                content_type='application/json')
        assert resp.status_code == 400

    def test_update_can_clear_override(self, auth_client):
        tpl = _create_template(auth_client, default_provider='zai',
                               default_model='glm-5.1')
        resp = auth_client.put(f"/api/v1/templates/{tpl['id']}",
                               data=json.dumps({'default_provider': '',
                                                'default_model': ''}),
                               content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()['template']
        assert data['default_provider'] == ''
        assert data['default_model'] == ''

    def test_update_ignores_reserved_keys(self, auth_client):
        tpl = _create_template(auth_client)
        # template_id/user_id dans le JSON ne doivent pas provoquer de 500
        resp = auth_client.put(f"/api/v1/templates/{tpl['id']}",
                               data=json.dumps({'name': 'Renomme',
                                                'template_id': 999,
                                                'user_id': 999}),
                               content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['template']['name'] == 'Renomme'

    def test_update_rejects_non_string_field(self, auth_client):
        tpl = _create_template(auth_client)
        resp = auth_client.put(f"/api/v1/templates/{tpl['id']}",
                               data=json.dumps({'name': 123}),
                               content_type='application/json')
        assert resp.status_code == 400


class TestGenerationDefaultResolution:
    """Resolution chain: request > template override > user general default."""

    def _set_user_default(self, app, db, provider_id):
        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            user.default_provider = provider_id
            db.session.commit()

    def test_general_default_applies_without_override(self, app, db, auth_client, llm_spy):
        with app.app_context():
            user_id = User.query.filter_by(username='admin').first().id
            _setup_provider(db, user_id, 'alibaba', 'qwen3.7-plus')
        self._set_user_default(app, db, 'alibaba')
        tpl = _create_template(auth_client)

        resp = auth_client.post('/api/v1/generate',
                                data=json.dumps({'template_id': tpl['id'],
                                                 'variables': {'nom': 'Quentin'}}),
                                content_type='application/json')
        assert resp.status_code == 200
        assert llm_spy[-1] == {'provider': 'alibaba', 'model': 'qwen3.7-plus'}

    def test_template_override_beats_general_default(self, app, db, auth_client, llm_spy):
        with app.app_context():
            user_id = User.query.filter_by(username='admin').first().id
            _setup_provider(db, user_id, 'alibaba', 'qwen3.7-plus')
            _setup_provider(db, user_id, 'zai', 'glm-5.1')
        self._set_user_default(app, db, 'alibaba')
        tpl = _create_template(auth_client, default_provider='zai',
                               default_model='glm-4.7')

        resp = auth_client.post('/api/v1/generate',
                                data=json.dumps({'template_id': tpl['id'],
                                                 'variables': {'nom': 'Q'}}),
                                content_type='application/json')
        assert resp.status_code == 200
        assert llm_spy[-1] == {'provider': 'zai', 'model': 'glm-4.7'}

    def test_request_choice_beats_everything(self, app, db, auth_client, llm_spy):
        with app.app_context():
            user_id = User.query.filter_by(username='admin').first().id
            _setup_provider(db, user_id, 'alibaba', 'qwen3.7-plus')
            _setup_provider(db, user_id, 'opencode', 'glm-5.1')
        tpl = _create_template(auth_client, default_provider='alibaba',
                               default_model='qwen3.6-plus')

        resp = auth_client.post('/api/v1/generate',
                                data=json.dumps({'template_id': tpl['id'],
                                                 'provider': 'opencode',
                                                 'model': 'minimax-m3',
                                                 'variables': {'nom': 'Q'}}),
                                content_type='application/json')
        assert resp.status_code == 200
        assert llm_spy[-1] == {'provider': 'opencode', 'model': 'minimax-m3'}

    def test_template_model_not_borrowed_by_other_provider(self, app, db, auth_client, llm_spy):
        """provider explicite sans modele : ne pas reprendre le modele d'un autre provider."""
        with app.app_context():
            user_id = User.query.filter_by(username='admin').first().id
            _setup_provider(db, user_id, 'opencode', 'kimi-k2.6')
        tpl = _create_template(auth_client, default_provider='zai',
                               default_model='glm-4.7')

        resp = auth_client.post('/api/v1/generate',
                                data=json.dumps({'template_id': tpl['id'],
                                                 'provider': 'opencode',
                                                 'variables': {'nom': 'Q'}}),
                                content_type='application/json')
        assert resp.status_code == 200
        assert llm_spy[-1] == {'provider': 'opencode', 'model': 'kimi-k2.6'}

    def test_no_provider_configured_returns_400(self, auth_client, llm_spy):
        tpl = _create_template(auth_client)
        resp = auth_client.post('/api/v1/generate',
                                data=json.dumps({'template_id': tpl['id'],
                                                 'variables': {'nom': 'Q'}}),
                                content_type='application/json')
        assert resp.status_code == 400
        assert 'provider' in resp.get_json()['error'].lower()

    def test_invalid_template_id_returns_400(self, auth_client, llm_spy):
        resp = auth_client.post('/api/v1/generate',
                                data=json.dumps({'template_id': 'abc',
                                                 'variables': {}}),
                                content_type='application/json')
        assert resp.status_code == 400


class TestProviderCatalog:
    """Provider definitions and up-to-date model lists."""

    def test_all_providers_registered(self, app):
        providers = app.config['PROVIDERS']
        assert set(providers) == {'zai', 'openrouter', 'alibaba', 'opencode'}
        assert providers['opencode']['api_url'] == 'https://opencode.ai/zen/go/v1/chat/completions'
        assert providers['opencode']['anthropic_url'] == 'https://opencode.ai/zen/go/v1/messages'
        assert providers['alibaba']['models_url'] is None

    def test_qwen37_plus_available_on_alibaba(self, app):
        from app.services.llm_service import _STATIC_MODELS
        ids = [m['id'] for m in _STATIC_MODELS['alibaba']]
        assert 'qwen3.7-plus' in ids
        assert app.config['PROVIDERS']['alibaba']['default_model'] == 'qwen3.7-plus'

    def test_static_lists_sorted_alphabetically(self):
        from app.services.llm_service import _STATIC_MODELS
        for provider_id, models in _STATIC_MODELS.items():
            names = [m['name'].lower() for m in models]
            assert names == sorted(names), f'{provider_id} non trie alphabetiquement'

    def test_opencode_anthropic_routing(self, app):
        from app.services.llm_service import _model_api_format
        with app.app_context():
            assert _model_api_format('opencode', 'minimax-m3') == 'anthropic'
            assert _model_api_format('opencode', 'qwen3.7-plus') == 'anthropic'
            assert _model_api_format('opencode', 'glm-5.1') == 'openai'
            assert _model_api_format('opencode', 'deepseek-v4-pro') == 'openai'
            # Heuristique pour un modele inconnu de la liste statique
            assert _model_api_format('opencode', 'qwen4-future') == 'anthropic'
            assert _model_api_format('zai', 'glm-5.1') == 'openai'
            assert _model_api_format('alibaba', 'qwen3.7-plus') == 'openai'

    def test_opencode_anthropic_request_build(self, app):
        from app.services.llm_service import _build_request
        with app.app_context():
            provider = app.config['PROVIDERS']['opencode']
            url, headers, payload, fmt = _build_request(
                provider, 'opencode', 'minimax-m3', 'sk-test', 'Bonjour', stream=False
            )
            assert fmt == 'anthropic'
            assert url == 'https://opencode.ai/zen/go/v1/messages'
            assert headers['x-api-key'] == 'sk-test'
            assert headers['anthropic-version'] == '2023-06-01'
            assert 'Authorization' not in headers
            assert payload['max_tokens'] == 8192

            url, headers, payload, fmt = _build_request(
                provider, 'opencode', 'glm-5.1', 'sk-test', 'Bonjour', stream=True
            )
            assert fmt == 'openai'
            assert url == 'https://opencode.ai/zen/go/v1/chat/completions'
            assert headers['Authorization'] == 'Bearer sk-test'
            assert payload['stream'] is True

    def test_fetch_models_static_fallback_sorted(self, app):
        """alibaba n'a pas d'endpoint /models : la liste statique est retournee triee."""
        from app.services.llm_service import fetch_models
        with app.test_request_context():
            models, error = fetch_models('alibaba', 'sk-test')
        assert error is None
        names = [m['name'].lower() for m in models]
        assert names == sorted(names)
        assert any(m['id'] == 'qwen3.7-plus' for m in models)


class TestOpenRedirect:
    """Le parametre next du login ne doit jamais rediriger hors du site."""

    def test_protocol_relative_url_rejected(self, client, admin_user):
        resp = client.post('/auth/login?next=//evil.com', data={
            'username': 'admin',
            'password': 'Admin123!',
        })
        assert resp.status_code == 302
        assert 'evil.com' not in resp.location

    def test_backslash_url_rejected(self, client, admin_user):
        resp = client.post('/auth/login?next=/\\evil.com', data={
            'username': 'admin',
            'password': 'Admin123!',
        })
        assert resp.status_code == 302
        assert 'evil.com' not in resp.location

    def test_control_char_url_rejected(self, client, admin_user):
        # /%09/evil.com -> '/\t/evil.com' : le navigateur retire le TAB et
        # interprete '//evil.com' comme une URL externe
        resp = client.post('/auth/login?next=/%09/evil.com', data={
            'username': 'admin',
            'password': 'Admin123!',
        })
        assert resp.status_code == 302
        assert 'evil.com' not in resp.location

    def test_internal_path_allowed(self, client, admin_user):
        resp = client.post('/auth/login?next=/template/new', data={
            'username': 'admin',
            'password': 'Admin123!',
        })
        assert resp.status_code == 302
        assert resp.location.endswith('/template/new')
