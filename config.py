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
    # Coding Plan endpoint: https://api.z.ai/api/coding/paas/v4
    # Standard API endpoint: https://api.z.ai/api/paas/v4
    PROVIDERS: dict = {
        'zai': {
            'name': 'Z.AI Coding Plan',
            'api_url': 'https://api.z.ai/api/coding/paas/v4/chat/completions',
            'models_url': 'https://api.z.ai/api/coding/paas/v4/models',
            'default_model': 'glm-4.7',
        },
        'openrouter': {
            'name': 'OpenRouter',
            'api_url': 'https://openrouter.ai/api/v1/chat/completions',
            'models_url': 'https://openrouter.ai/api/v1/models',
            'default_model': 'anthropic/claude-3.5-sonnet',
        },
        'alibaba': {
            'name': 'Alibaba Cloud Coding Plan',
            'api_url': 'https://coding-intl.dashscope.aliyuncs.com/v1/chat/completions',
            'models_url': 'https://coding-intl.dashscope.aliyuncs.com/v1/models',
            'default_model': 'qwen3.6-plus',
        },
    }

    # History pagination
    HISTORY_PER_PAGE: int = 20
    HISTORY_MAX_ENTRIES: int = 500

    # Default meta-prompt for AI template content generation
    DEFAULT_META_PROMPT: str = (
        "Tu es un expert en prompt engineering. A partir du nom et de la description d'un template, "
        "genere le contenu complet du prompt.\n\n"
        "Le prompt genere DOIT:\n"
        "- Utiliser des variables entre accolades {comme_ceci} aux endroits ou l'utilisateur devra fournir des informations\n"
        "- Etre detaille, structure et professionnel\n"
        "- Contenir des instructions claires pour un LLM\n"
        "- Etre en francais\n\n"
        "Nom du template: {nom_template}\n"
        "Description du template: {description_template}\n\n"
        "Genere UNIQUEMENT le contenu du prompt, sans explication ni commentaire."
    )


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
