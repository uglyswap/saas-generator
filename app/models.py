"""Database models for SaaS Generator."""
from datetime import datetime, timezone
from typing import Optional

from flask_login import UserMixin

from app import db


class User(UserMixin, db.Model):
    """User account model."""
    __tablename__ = 'users'

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email: str = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash: str = db.Column(db.String(255), nullable=False)
    is_admin: bool = db.Column(db.Boolean, default=False)
    created_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    templates = db.relationship(
        'Template', backref='owner', lazy='dynamic', cascade='all, delete-orphan'
    )
    history_entries = db.relationship(
        'HistoryEntry', backref='owner', lazy='dynamic', cascade='all, delete-orphan'
    )
    provider_configs = db.relationship(
        'ProviderConfig', backref='owner', lazy='dynamic', cascade='all, delete-orphan'
    )

    def __repr__(self) -> str:
        return f'<User {self.username}>'


class Template(db.Model):
    """Prompt template model."""
    __tablename__ = 'templates'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name: str = db.Column(db.String(200), nullable=False)
    description: str = db.Column(db.Text, default='')
    content: str = db.Column(db.Text, nullable=False)
    variables: list = db.Column(db.JSON, default=list)
    default_provider: str = db.Column(db.String(50), default='zai')
    default_model: str = db.Column(db.String(100), default='glm-4.7')
    created_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    history_entries = db.relationship('HistoryEntry', backref='template', lazy='dynamic')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'content': self.content,
            'variables': self.variables or [],
            'default_provider': self.default_provider,
            'default_model': self.default_model,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f'<Template {self.name}>'


class HistoryEntry(db.Model):
    """Generation history entry."""
    __tablename__ = 'history_entries'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    template_id: Optional[int] = db.Column(db.Integer, db.ForeignKey('templates.id'), nullable=True)
    template_name: str = db.Column(db.String(200))
    variables: dict = db.Column(db.JSON, default=dict)
    provider: str = db.Column(db.String(50))
    model: str = db.Column(db.String(100))
    result: str = db.Column(db.Text)
    created_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'template_id': self.template_id,
            'template_name': self.template_name or '',
            'variables': self.variables or {},
            'provider': self.provider or '',
            'model': self.model or '',
            'result': self.result or '',
            'timestamp': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f'<HistoryEntry {self.id}>'


class ProviderConfig(db.Model):
    """Per-user LLM provider configuration."""
    __tablename__ = 'provider_configs'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider_id: str = db.Column(db.String(50), nullable=False)
    api_key_encrypted: str = db.Column(db.Text, default='')
    selected_model: str = db.Column(db.String(100), default='')
    models_cache: list = db.Column(db.JSON, default=list)
    updated_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'provider_id', name='uq_user_provider'),
    )

    def __repr__(self) -> str:
        return f'<ProviderConfig {self.provider_id} user={self.user_id}>'
