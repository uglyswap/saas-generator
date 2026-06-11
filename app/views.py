"""Frontend views blueprint - renders HTML pages."""
import logging
from flask import Blueprint, render_template, abort, current_app
from flask_login import login_required, current_user

from app.models import ProviderConfig
from app.services.config_service import get_user_default
from app.services.template_service import get_user_templates, get_template
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

    # Determine selected provider/model from the user's general default
    selected_provider, selected_model = get_user_default(user_id)
    if not selected_provider:
        # Nothing configured yet: present the first known provider with its default model
        selected_provider = next(iter(providers), '')
        selected_model = providers.get(selected_provider, {}).get('default_model', '') if selected_provider else ''

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
