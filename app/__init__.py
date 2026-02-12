"""Application factory for SaaS Generator."""
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


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

    # Load configuration
    from config import config_map
    app.config.from_object(config_map.get(config_name, config_map['default']))

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

        # Auto-migrate: add edited_at column if missing
        from sqlalchemy import inspect as sa_inspect, text
        inspector = sa_inspect(db.engine)
        if 'history_entries' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('history_entries')]
            if 'edited_at' not in columns:
                db.session.execute(text('ALTER TABLE history_entries ADD COLUMN edited_at DATETIME'))
                db.session.commit()
                app.logger.info('Migration: added edited_at column to history_entries')

        # Auto-migrate: add default_provider column to users if missing
        if 'users' in inspector.get_table_names():
            user_columns = [c['name'] for c in inspector.get_columns('users')]
            if 'default_provider' not in user_columns:
                db.session.execute(text('ALTER TABLE users ADD COLUMN default_provider VARCHAR(50)'))
                db.session.commit()
                app.logger.info('Migration: added default_provider column to users')

            # Auto-migrate: add meta_prompt columns to users if missing
            for col_name, col_type in [
                ('meta_prompt', 'TEXT'),
                ('meta_prompt_provider', 'VARCHAR(50)'),
                ('meta_prompt_model', 'VARCHAR(100)'),
            ]:
                if col_name not in user_columns:
                    db.session.execute(text(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}'))
                    db.session.commit()
                    app.logger.info('Migration: added %s column to users', col_name)

    app.logger.info('SaaS Generator started (%s mode)', config_name)
    return app
