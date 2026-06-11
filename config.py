"""Application configuration classes."""
import os
from dotenv import load_dotenv

load_dotenv()

# Fallback de developpement : create_app refuse de demarrer en production avec cette valeur
DEFAULT_SECRET_KEY = 'dev-change-me-in-production'

# Valeurs sentinelles publiques (depot, .env.example, anciens fallbacks docker-compose) :
# toutes refusees en production, pas seulement le defaut courant
INSECURE_SECRET_KEYS = frozenset({
    DEFAULT_SECRET_KEY,
    'change-me-to-a-long-random-string',
    'change-me-in-production',
    'votre-cle-secrete-tres-longue',
})


class Config:
    """Base configuration."""
    SECRET_KEY: str = os.environ.get('SECRET_KEY', DEFAULT_SECRET_KEY)
    SQLALCHEMY_DATABASE_URI: str = os.environ.get('DATABASE_URL', 'sqlite:///saas_generator.db')
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    WTF_CSRF_ENABLED: bool = True
    WTF_CSRF_TIME_LIMIT: int = 3600
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16 MB
    ENCRYPTION_KEY: str = os.environ.get('ENCRYPTION_KEY', '')
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = 'Lax'
    REMEMBER_COOKIE_HTTPONLY: bool = True
    RATELIMIT_ENABLED: bool = True

    # LLM Provider definitions
    # - api_url : endpoint OpenAI-compatible (chat/completions)
    # - anthropic_url : endpoint Anthropic-compatible (messages), si le provider route
    #   certains modeles dessus (cf. _STATIC_MODELS dans llm_service.py)
    # - models_url : endpoint GET de listing dynamique, None si inexistant
    PROVIDERS: dict = {
        'zai': {
            'name': 'Z.AI Coding Plan',
            'api_url': 'https://api.z.ai/api/coding/paas/v4/chat/completions',
            'models_url': 'https://api.z.ai/api/coding/paas/v4/models',
            'default_model': 'glm-5.1',
        },
        'openrouter': {
            'name': 'OpenRouter',
            'api_url': 'https://openrouter.ai/api/v1/chat/completions',
            'models_url': 'https://openrouter.ai/api/v1/models',
            'default_model': 'anthropic/claude-sonnet-4.6',
        },
        'alibaba': {
            'name': 'Alibaba Cloud Coding Plan',
            'api_url': 'https://coding-intl.dashscope.aliyuncs.com/v1/chat/completions',
            # Pas d'endpoint GET /models sur le Coding Plan (404 verifie) :
            # la liste statique de llm_service.py est la seule source
            'models_url': None,
            'default_model': 'qwen3.7-plus',
        },
        'opencode': {
            'name': 'OpenCode Go',
            'api_url': 'https://opencode.ai/zen/go/v1/chat/completions',
            'anthropic_url': 'https://opencode.ai/zen/go/v1/messages',
            'models_url': 'https://opencode.ai/zen/go/v1/models',
            'default_model': 'glm-5.1',
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
    RATELIMIT_ENABLED: bool = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG: bool = False
    # Cookies servis uniquement en HTTPS ; mettre SESSION_COOKIE_SECURE=false
    # dans l'environnement pour un deploiement HTTP local
    SESSION_COOKIE_SECURE: bool = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() != 'false'
    REMEMBER_COOKIE_SECURE: bool = SESSION_COOKIE_SECURE


config_map: dict = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': ProductionConfig,
}
