"""Tests for API v1 endpoints."""
import json
import pytest


class TestTemplatesAPI:
    """Test template CRUD via API."""

    def test_list_templates_empty(self, auth_client):
        resp = auth_client.get('/api/v1/templates')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['templates'] == []

    def test_create_template(self, auth_client):
        resp = auth_client.post('/api/v1/templates',
            data=json.dumps({
                'name': 'Test Template',
                'content': 'Hello {name}, welcome to {city}',
                'description': 'A test template',
            }),
            content_type='application/json',
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['template']['name'] == 'Test Template'
        assert 'name' in data['template']['variables']
        assert 'city' in data['template']['variables']

    def test_create_template_missing_name(self, auth_client):
        resp = auth_client.post('/api/v1/templates',
            data=json.dumps({'content': 'test'}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_create_template_missing_content(self, auth_client):
        resp = auth_client.post('/api/v1/templates',
            data=json.dumps({'name': 'test'}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_update_template(self, auth_client):
        # Create first
        resp = auth_client.post('/api/v1/templates',
            data=json.dumps({'name': 'Original', 'content': 'Hello {x}'}),
            content_type='application/json',
        )
        tpl_id = resp.get_json()['template']['id']

        # Update
        resp = auth_client.put(f'/api/v1/templates/{tpl_id}',
            data=json.dumps({'name': 'Updated', 'content': 'Hi {y}'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['template']['name'] == 'Updated'
        assert 'y' in data['template']['variables']

    def test_delete_template(self, auth_client):
        resp = auth_client.post('/api/v1/templates',
            data=json.dumps({'name': 'ToDelete', 'content': 'bye'}),
            content_type='application/json',
        )
        tpl_id = resp.get_json()['template']['id']

        resp = auth_client.delete(f'/api/v1/templates/{tpl_id}')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_delete_nonexistent_template(self, auth_client):
        resp = auth_client.delete('/api/v1/templates/99999')
        assert resp.status_code == 404


class TestHistoryAPI:
    """Test history endpoints."""

    def test_list_history_empty(self, auth_client):
        resp = auth_client.get('/api/v1/history')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['entries'] == []
        assert data['total'] == 0

    def test_history_pagination_params(self, auth_client):
        resp = auth_client.get('/api/v1/history?page=1&per_page=5')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'page' in data
        assert 'pages' in data
        assert 'per_page' in data


class TestConfigAPI:
    """Test configuration endpoints."""

    def test_get_config(self, auth_client):
        resp = auth_client.get('/api/v1/config')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'providers' in data
        assert 'zai' in data['providers']
        assert 'openrouter' in data['providers']

    def test_save_config_invalid_provider(self, auth_client):
        resp = auth_client.post('/api/v1/config',
            data=json.dumps({'provider': 'invalid_provider', 'api_key': 'test'}),
            content_type='application/json',
        )
        assert resp.status_code == 400


class TestMultiUser:
    """Test data isolation between users."""

    def test_user_cannot_see_other_templates(self, app, db, client):
        from app.models import User, Template
        from app.utils.security import hash_password

        with app.app_context():
            # Create two users
            u1 = User(username='user1', email='u1@t.com', password_hash=hash_password('User1234!'))
            u2 = User(username='user2', email='u2@t.com', password_hash=hash_password('User2345!'))
            db.session.add_all([u1, u2])
            db.session.commit()

            # Create template for user1
            t1 = Template(user_id=u1.id, name='User1 Template', content='private {data}', variables=['data'])
            db.session.add(t1)
            db.session.commit()

            # Capture the id before leaving the context
            t1_id = t1.id

        # Login as user2
        client.post('/auth/login', data={'username': 'user2', 'password': 'User2345!'})

        # User2 should see empty templates
        resp = client.get('/api/v1/templates')
        data = resp.get_json()
        assert len(data['templates']) == 0

        # User2 cannot access user1's template
        resp = client.get(f'/template/{t1_id}')
        assert resp.status_code == 404


class TestHealth:
    """Healthcheck endpoint (non authentifie)."""

    def test_health_ok(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ok'


class TestUnauthorized:
    """Test endpoints require authentication."""

    def test_dashboard_requires_login(self, client, admin_user):
        resp = client.get('/')
        assert resp.status_code == 302
        assert '/auth/login' in resp.location

    def test_api_requires_login(self, client, admin_user):
        resp = client.get('/api/v1/templates')
        assert resp.status_code == 302
