"""Tests for authentication system."""
import pytest


class TestSetup:
    """Test first-run setup."""

    def test_redirects_to_setup_when_no_users(self, client, db):
        resp = client.get('/')
        assert resp.status_code == 302
        assert '/auth/setup' in resp.location

    def test_setup_page_loads(self, client, db):
        resp = client.get('/auth/setup')
        assert resp.status_code == 200
        assert b'Configuration initiale' in resp.data

    def test_setup_creates_admin(self, client, db):
        resp = client.post('/auth/setup', data={
            'username': 'admin',
            'email': 'admin@test.com',
            'password': 'Admin123!',
            'password_confirm': 'Admin123!',
        })
        assert resp.status_code == 302

        from app.models import User
        user = User.query.filter_by(username='admin').first()
        assert user is not None
        assert user.is_admin is True

    def test_setup_blocked_after_first_user(self, client, admin_user):
        resp = client.get('/auth/setup')
        assert resp.status_code == 302
        assert '/auth/login' in resp.location


class TestLogin:
    """Test login flow."""

    def test_login_page_loads(self, client, admin_user):
        resp = client.get('/auth/login')
        assert resp.status_code == 200
        assert b'Connexion' in resp.data

    def test_login_with_valid_credentials(self, client, admin_user):
        resp = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'Admin123!',
        })
        assert resp.status_code == 302

    def test_login_with_email(self, client, admin_user):
        resp = client.post('/auth/login', data={
            'username': 'admin@test.com',
            'password': 'Admin123!',
        })
        assert resp.status_code == 302

    def test_login_with_wrong_password(self, client, admin_user):
        resp = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'wrong',
        })
        assert resp.status_code == 401

    def test_login_with_unknown_user(self, client, admin_user):
        resp = client.post('/auth/login', data={
            'username': 'nobody',
            'password': 'Admin123!',
        })
        assert resp.status_code == 401


class TestRegister:
    """Test registration flow."""

    def test_register_page_loads(self, client, admin_user):
        resp = client.get('/auth/register')
        assert resp.status_code == 200

    def test_register_new_user(self, client, admin_user):
        resp = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'new@test.com',
            'password': 'NewUser123!',
            'password_confirm': 'NewUser123!',
        })
        assert resp.status_code == 302

        from app.models import User
        user = User.query.filter_by(username='newuser').first()
        assert user is not None
        assert user.is_admin is False

    def test_register_duplicate_username(self, client, admin_user):
        resp = client.post('/auth/register', data={
            'username': 'admin',
            'email': 'other@test.com',
            'password': 'Test1234!',
            'password_confirm': 'Test1234!',
        })
        assert resp.status_code == 409

    def test_register_password_mismatch(self, client, admin_user):
        resp = client.post('/auth/register', data={
            'username': 'test2',
            'email': 't2@test.com',
            'password': 'Test1234!',
            'password_confirm': 'Different1!',
        })
        assert resp.status_code == 400

    def test_register_weak_password(self, client, admin_user):
        resp = client.post('/auth/register', data={
            'username': 'test3',
            'email': 't3@test.com',
            'password': 'short',
            'password_confirm': 'short',
        })
        assert resp.status_code == 400


class TestLogout:
    """Test logout."""

    def test_logout(self, auth_client):
        resp = auth_client.get('/auth/logout')
        assert resp.status_code == 302

        resp = auth_client.get('/')
        assert resp.status_code == 302
        assert '/auth/login' in resp.location
