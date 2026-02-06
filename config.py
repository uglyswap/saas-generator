"""Application configuration classes."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""
    SECRET_KEY: str = os.environ.get('SECRET_KEY', 'dev-change-me-in-production')
    SQLALCHEMY_DATABASE_URI: str = os.environ.get('DATABASE_URL', 'sqlite:///saas_generator.db')
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    WTF_CSRF_ENABLED: bool = True
    WTF_CSRF_TIME_LIMIT: int = 3600
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16 MB
    ENCRYPTION_KEY: str = os.environ.get('ENCRYPTION_KEY', '')

    # LLM Provider definitions
    PROVIDERS: dict = {
        'zai': {
            'name': 'Z.AI',
            'api_url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
            'models_url': 'https://open.bigmodel.cn/api/paas/v4/models',
            'default_model': 'glm-4.7',
        },
        'openrouter': {
            'name': 'OpenRouter',
            'api_url': 'https://openrouter.ai/api/v1/chat/completions',
            'models_url': 'https://openrouter.ai/api/v1/models',
            'default_model': 'anthropic/claude-3.5-sonnet',
        },
    }

    # History pagination
    HISTORY_PER_PAGE: int = 20
    HISTORY_MAX_ENTRIES: int = 500


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG: bool = True
    SQLALCHEMY_DATABASE_URI: str = os.environ.get('DATABASE_URL', 'sqlite:///saas_generator_dev.db')


class TestingConfig(Config):
    """Testing configuration."""
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED: bool = False
    SECRET_KEY: str = 'test-secret-key-do-not-use-in-prod'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG: bool = False


config_map: dict = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': ProductionConfig,
}
