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
    default_provider: str = db.Column(db.String(50), nullable=True)
    meta_prompt: str = db.Column(db.Text, default='')
    meta_prompt_provider: str = db.Column(db.String(50), nullable=True)
    meta_prompt_model: str = db.Column(db.String(100), nullable=True)
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
    # NULL = pas d'override : le defaut general de l'utilisateur s'applique
    default_provider: Optional[str] = db.Column(db.String(50), nullable=True, default=None)
    default_model: Optional[str] = db.Column(db.String(100), nullable=True, default=None)
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
            'default_provider': self.default_provider or '',
            'default_model': self.default_model or '',
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
    edited_at: Optional[datetime] = db.Column(db.DateTime, nullable=True)

    versions = db.relationship('GenerationVersion', backref='history_entry', lazy='dynamic',
                               cascade='all, delete-orphan', order_by='GenerationVersion.version_number')

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
            'edited_at': self.edited_at.isoformat() if self.edited_at else None,
        }

    def __repr__(self) -> str:
        return f'<HistoryEntry {self.id}>'


class GenerationVersion(db.Model):
    """Versioned snapshot of a generation result."""
    __tablename__ = 'generation_versions'

    id: int = db.Column(db.Integer, primary_key=True)
    history_entry_id: int = db.Column(db.Integer, db.ForeignKey('history_entries.id'), nullable=False, index=True)
    version_number: int = db.Column(db.Integer, nullable=False)
    result: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('history_entry_id', 'version_number', name='uq_entry_version'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'history_entry_id': self.history_entry_id,
            'version_number': self.version_number,
            'result': self.result or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f'<GenerationVersion entry={self.history_entry_id} v{self.version_number}>'


class ExportTemplate(db.Model):
    """User-defined branding template for exports."""
    __tablename__ = 'export_templates'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name: str = db.Column(db.String(200), nullable=False)
    header_text: str = db.Column(db.String(500), default='')
    footer_text: str = db.Column(db.String(500), default='')
    primary_color: str = db.Column(db.String(20), default='#2563eb')
    logo_path: Optional[str] = db.Column(db.String(500), nullable=True)
    created_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'header_text': self.header_text or '',
            'footer_text': self.footer_text or '',
            'primary_color': self.primary_color or '#2563eb',
            'logo_path': self.logo_path or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f'<ExportTemplate {self.name}>'


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
