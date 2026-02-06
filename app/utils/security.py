"""Security utilities for encryption and password hashing."""
import base64
import hashlib
import logging
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Get a Fernet instance for symmetric encryption.

    Uses ENCRYPTION_KEY from config if set, otherwise derives one
    from SECRET_KEY via SHA-256.
    """
    key = current_app.config.get('ENCRYPTION_KEY', '')
    if key:
        raw = key.encode() if isinstance(key, str) else key
    else:
        secret = current_app.config['SECRET_KEY']
        key_bytes = hashlib.sha256(secret.encode()).digest()
        raw = base64.urlsafe_b64encode(key_bytes)
    return Fernet(raw)


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key for safe storage in the database."""
    if not api_key:
        return ''
    try:
        f = _get_fernet()
        return f.encrypt(api_key.encode()).decode()
    except Exception:
        logger.error('Failed to encrypt API key', exc_info=True)
        return ''


def decrypt_api_key(encrypted: str) -> str:
    """Decrypt an API key from the database."""
    if not encrypted:
        return ''
    try:
        f = _get_fernet()
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        logger.warning('Invalid encryption token - key may have changed')
        return ''
    except Exception:
        logger.error('Failed to decrypt API key', exc_info=True)
        return ''


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False
