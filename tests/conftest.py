"""Pytest fixtures for SaaS Generator tests."""
import pytest
from app import create_app, db as _db
from app.models import User
from app.utils.security import hash_password


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    app = create_app('testing')
    return app


@pytest.fixture(scope='function')
def db(app):
    """Provide a clean database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture
def client(app, db):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def admin_user(app, db):
    """Create and return an admin user."""
    with app.app_context():
        user = User(
            username='admin',
            email='admin@test.com',
            password_hash=hash_password('Admin123!'),
            is_admin=True,
        )
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def regular_user(app, db):
    """Create and return a regular user."""
    with app.app_context():
        user = User(
            username='testuser',
            email='user@test.com',
            password_hash=hash_password('User1234!'),
        )
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def auth_client(client, admin_user):
    """Test client logged in as admin."""
    client.post('/auth/login', data={
        'username': 'admin',
        'password': 'Admin123!',
    })
    return client
