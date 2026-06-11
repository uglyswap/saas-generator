"""Application factory for SaaS Generator."""
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
# memory:// = compteurs par worker ; pointer RATELIMIT_STORAGE_URI vers Redis
# en multi-workers pour des limites globales exactes
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'),
)


def create_app(config_name: Optional[str] = None) -> Flask:
    """Create and configure the Flask application."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'production')

    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    app = Flask(
        __name__,
        template_folder=os.path.join(basedir, 'templates'),
        static_folder=os.path.join(basedir, 'static'),
    )

    # Load configuration. La garde se base sur la CLASSE resolue, pas sur le nom :
    # tout config_name inconnu retombe sur ProductionConfig et doit etre garde aussi.
    from config import config_map, INSECURE_SECRET_KEYS, ProductionConfig
    config_class = config_map.get(config_name, config_map['default'])
    app.config.from_object(config_class)
    is_production = issubclass(config_class, ProductionConfig)

    # Garde-fou production : refuser tout SECRET_KEY sentinelle connu (sessions
    # forgeables, chiffrement des cles API derive d'un secret public)
    if is_production and app.config.get('SECRET_KEY') in INSECURE_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY manquant ou non securise en production. Definissez la variable "
            "d'environnement SECRET_KEY (generation : "
            "python -c \"import secrets; print(secrets.token_hex(32))\")."
        )

    # Derriere un reverse proxy (nginx, traefik...) : TRUST_PROXY=true pour que
    # remote_addr (rate limiting) et le scheme refletent le client reel
    if os.environ.get('TRUST_PROXY', '').lower() in ('1', 'true', 'yes'):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # JSON configuration
    app.config['JSON_AS_ASCII'] = False
    app.config['JSON_SORT_KEYS'] = False

    # -------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------
    log_level = logging.DEBUG if app.debug else logging.INFO
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # File handler with rotation
    log_path = os.path.join(basedir, 'app.log')
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    app.logger.handlers.clear()
    app.logger.addHandler(console_handler)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(log_level)

    # Silence noisy libraries
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    # -------------------------------------------------------------------
    # Extensions
    # -------------------------------------------------------------------
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    if is_production and not app.config.get('ENCRYPTION_KEY'):
        app.logger.warning(
            "ENCRYPTION_KEY non defini : la cle de chiffrement des cles API est derivee de "
            "SECRET_KEY. Definissez ENCRYPTION_KEY (Fernet.generate_key()) pour pouvoir faire "
            "tourner les deux secrets independamment."
        )

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'warning'

    # -------------------------------------------------------------------
    # User loader
    # -------------------------------------------------------------------
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str) -> Optional[User]:
        return db.session.get(User, int(user_id))

    # -------------------------------------------------------------------
    # Blueprints
    # -------------------------------------------------------------------
    from app.auth import auth_bp
    from app.views import views_bp
    from app.api_v1 import api_v1_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_v1_bp, url_prefix='/api/v1')

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Return JSON for CSRF errors on API calls."""
        return jsonify({'error': 'Session expiree. Rafraichissez la page (F5).'}), 400

    # -------------------------------------------------------------------
    # Database initialisation
    # -------------------------------------------------------------------
    with app.app_context():
        db.create_all()
        os.makedirs(os.path.join(basedir, 'exports'), exist_ok=True)

        # Auto-migrations idempotentes. Le try/except est indispensable : sous
        # gunicorn multi-workers (sans --preload), chaque worker execute ce bloc
        # en parallele et le perdant de la course leve 'duplicate column name'.
        from sqlalchemy import inspect as sa_inspect, text

        def _add_column_if_missing(table: str, column: str, col_type: str) -> None:
            try:
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'))
                db.session.commit()
                app.logger.info('Migration: added %s column to %s', column, table)
            except Exception as exc:
                db.session.rollback()
                # Attendu en multi-workers (colonne deja ajoutee par un autre worker) ;
                # logge pour ne pas masquer une vraie erreur (DB verrouillee, disque plein)
                app.logger.warning('Migration %s.%s ignoree : %s', table, column, exc)

        inspector = sa_inspect(db.engine)
        if 'history_entries' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('history_entries')]
            if 'edited_at' not in columns:
                _add_column_if_missing('history_entries', 'edited_at', 'DATETIME')

        if 'users' in inspector.get_table_names():
            user_columns = [c['name'] for c in inspector.get_columns('users')]
            for col_name, col_type in [
                ('default_provider', 'VARCHAR(50)'),
                ('meta_prompt', 'TEXT'),
                ('meta_prompt_provider', 'VARCHAR(50)'),
                ('meta_prompt_model', 'VARCHAR(100)'),
            ]:
                if col_name not in user_columns:
                    _add_column_if_missing('users', col_name, col_type)

        # Migration des templates herites : avant l'introduction du defaut general,
        # chaque template recevait 'zai'/'glm-4.7' en dur sans choix de l'utilisateur.
        # On remet ce couple exact a NULL pour que le defaut general s'applique
        # (un override choisi sur un autre couple n'est pas touche).
        if 'templates' in inspector.get_table_names():
            try:
                result = db.session.execute(text(
                    "UPDATE templates SET default_provider = NULL, default_model = NULL "
                    "WHERE default_provider = 'zai' AND default_model = 'glm-4.7'"
                ))
                db.session.commit()
                if result.rowcount:
                    app.logger.info(
                        'Migration: %d template(s) herites zai/glm-4.7 remis au defaut general',
                        result.rowcount,
                    )
            except Exception as exc:
                db.session.rollback()
                app.logger.warning('Migration des defauts de templates ignoree : %s', exc)

    app.logger.info('SaaS Generator started (%s mode)', config_name)
    return app
