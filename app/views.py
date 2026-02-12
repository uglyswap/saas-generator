"""Frontend views blueprint - renders HTML pages."""
import logging
from flask import Blueprint, render_template, abort, current_app
from flask_login import login_required, current_user

from app import db
from app.models import ProviderConfig, User
from app.services.template_service import get_user_templates, get_template
from app.utils.security import decrypt_api_key
from app.utils.validators import extract_variables

logger = logging.getLogger(__name__)
views_bp = Blueprint('views', __name__)


def _build_config_for_frontend(user_id: int) -> dict:
    """Build a safe config dict for passing to templates (no raw API keys)."""
    providers_config = {}
    providers = current_app.config.get('PROVIDERS', {})

    for pid, pinfo in providers.items():
        pc = ProviderConfig.query.filter_by(user_id=user_id, provider_id=pid).first()
        providers_config[pid] = {
            'name': pinfo['name'],
            'has_api_key': bool(pc and pc.api_key_encrypted),
            'selected_model': pc.selected_model if pc else pinfo.get('default_model', ''),
            'models': (pc.models_cache if pc else []) or [],
        }

    # Determine selected provider/model from user's explicit default
    user = db.session.get(User, user_id)
    selected_provider = 'zai'
    selected_model = 'glm-4.7'

    if user and user.default_provider and user.default_provider in providers:
        selected_provider = user.default_provider
        pc = ProviderConfig.query.filter_by(user_id=user_id, provider_id=selected_provider).first()
        if pc and pc.selected_model:
            selected_model = pc.selected_model
    else:
        # Fallback: find first provider with a selected model
        for pid in providers:
            pc = ProviderConfig.query.filter_by(user_id=user_id, provider_id=pid).first()
            if pc and pc.selected_model:
                selected_provider = pid
                selected_model = pc.selected_model
                break

    return {
        'providers': providers_config,
        'selected_provider': selected_provider,
        'selected_model': selected_model,
    }


@views_bp.route('/')
@login_required
def index():
    """Dashboard - list templates."""
    templates = get_user_templates(current_user.id)
    config = _build_config_for_frontend(current_user.id)
    return render_template('index.html', templates=templates, config=config)


@views_bp.route('/template/new')
@login_required
def new_template():
    """Create template page."""
    config = _build_config_for_frontend(current_user.id)
    return render_template('template_form.html', template=None, config=config)


@views_bp.route('/template/<int:template_id>')
@login_required
def use_template(template_id: int):
    """Use template page - fill variables and generate."""
    tpl = get_template(template_id, current_user.id)
    if not tpl:
        abort(404)
    variables = extract_variables(tpl.content)
    config = _build_config_for_frontend(current_user.id)
    return render_template('use_template.html', template=tpl, variables=variables, config=config)


@views_bp.route('/template/<int:template_id>/edit')
@login_required
def edit_template(template_id: int):
    """Edit template page."""
    tpl = get_template(template_id, current_user.id)
    if not tpl:
        abort(404)
    config = _build_config_for_frontend(current_user.id)
    return render_template('template_form.html', template=tpl, config=config)
