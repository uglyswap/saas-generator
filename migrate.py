"""Migration script: imports data from legacy JSON files into SQLite.

Usage:
    python migrate.py [--username admin] [--email admin@example.com] [--password Admin123]

This script:
1. Creates the database tables
2. Creates an admin user (or uses existing)
3. Imports templates from templates.json
4. Imports history from history.json
5. Imports API keys from config.json (encrypted)
"""
import os
import sys
import json
import argparse
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description='Migrate JSON data to SQLite')
    parser.add_argument('--username', default='admin', help='Admin username')
    parser.add_argument('--email', default='admin@local.app', help='Admin email')
    parser.add_argument('--password', default='Admin123!', help='Admin password')
    args = parser.parse_args()

    from app import create_app, db
    from app.models import User, Template, HistoryEntry, ProviderConfig
    from app.utils.security import hash_password, encrypt_api_key

    app = create_app('development')

    with app.app_context():
        db.create_all()
        logger.info('Database tables created.')

        # ---------------------------------------------------------------
        # 1. Create or get admin user
        # ---------------------------------------------------------------
        user = User.query.filter_by(username=args.username).first()
        if not user:
            user = User(
                username=args.username,
                email=args.email,
                password_hash=hash_password(args.password),
                is_admin=True,
            )
            db.session.add(user)
            db.session.commit()
            logger.info('Admin user created: %s / %s', args.username, args.password)
        else:
            logger.info('Admin user already exists: %s', args.username)

        # ---------------------------------------------------------------
        # 2. Import templates from templates.json
        # ---------------------------------------------------------------
        templates_file = os.path.join(os.path.dirname(__file__), 'templates.json')
        if os.path.exists(templates_file):
            try:
                with open(templates_file, 'r', encoding='utf-8') as f:
                    legacy_templates = json.load(f)
                count = 0
                for lt in legacy_templates:
                    # Skip if template with same name already exists for this user
                    existing = Template.query.filter_by(
                        user_id=user.id, name=lt.get('name', '')
                    ).first()
                    if existing:
                        continue
                    tpl = Template(
                        user_id=user.id,
                        name=lt.get('name', 'Imported Template'),
                        description=lt.get('description', ''),
                        content=lt.get('content', ''),
                        variables=lt.get('variables', []),
                        default_provider=lt.get('default_provider', 'zai'),
                        default_model=lt.get('default_model', 'glm-4.7'),
                    )
                    db.session.add(tpl)
                    count += 1
                db.session.commit()
                logger.info('Imported %d templates from templates.json', count)
            except (json.JSONDecodeError, KeyError) as e:
                logger.error('Error reading templates.json: %s', e)
        else:
            logger.info('No templates.json found, skipping.')

        # ---------------------------------------------------------------
        # 3. Import history from history.json
        # ---------------------------------------------------------------
        history_file = os.path.join(os.path.dirname(__file__), 'history.json')
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    legacy_history = json.load(f)
                count = 0
                for lh in legacy_history:
                    # Find matching template by name
                    tpl = Template.query.filter_by(
                        user_id=user.id, name=lh.get('template_name', '')
                    ).first()
                    # Parse timestamp from legacy format
                    ts = lh.get('timestamp', '')
                    created_at = None
                    if ts:
                        try:
                            created_at = datetime.fromisoformat(ts)
                        except (ValueError, TypeError):
                            pass

                    entry = HistoryEntry(
                        user_id=user.id,
                        template_id=tpl.id if tpl else None,
                        template_name=lh.get('template_name', ''),
                        variables=lh.get('variables', {}),
                        provider=lh.get('provider', ''),
                        model=lh.get('model', ''),
                        result=lh.get('result', ''),
                    )
                    if created_at:
                        entry.created_at = created_at
                    db.session.add(entry)
                    count += 1
                db.session.commit()
                logger.info('Imported %d history entries from history.json', count)
            except (json.JSONDecodeError, KeyError) as e:
                logger.error('Error reading history.json: %s', e)
        else:
            logger.info('No history.json found, skipping.')

        # ---------------------------------------------------------------
        # 4. Import API keys from config.json
        # ---------------------------------------------------------------
        config_file = os.path.join(os.path.dirname(__file__), 'config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    legacy_config = json.load(f)
                for pid, pdata in legacy_config.get('providers', {}).items():
                    api_key = pdata.get('api_key', '')
                    if not api_key:
                        continue
                    pc = ProviderConfig.query.filter_by(
                        user_id=user.id, provider_id=pid
                    ).first()
                    if not pc:
                        pc = ProviderConfig(user_id=user.id, provider_id=pid)
                        db.session.add(pc)
                    pc.api_key_encrypted = encrypt_api_key(api_key)
                    pc.selected_model = pdata.get('default_model', '')
                    pc.models_cache = pdata.get('models', [])
                db.session.commit()
                logger.info('Imported API keys from config.json (encrypted)')
            except (json.JSONDecodeError, KeyError) as e:
                logger.error('Error reading config.json: %s', e)
        else:
            logger.info('No config.json found, skipping.')

        logger.info('')
        logger.info('Migration complete!')
        logger.info('Start the app with: python run.py')
        logger.info('Login with: %s / %s', args.username, args.password)


if __name__ == '__main__':
    main()
