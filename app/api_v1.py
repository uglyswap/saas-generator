"""API v1 blueprint - RESTful endpoints for templates, generation, history, config."""
import logging
from flask import Blueprint, request, jsonify, Response, current_app
from flask_login import login_required, current_user

from app import db
from app.models import ProviderConfig, Template
from app.utils.security import encrypt_api_key, decrypt_api_key
from app.utils.validators import (
    validate_api_key,
    validate_provider_id,
    validate_variable_values,
    safe_substitute,
    extract_variables,
)
from app.services.llm_service import call_llm_api, stream_llm_api, fetch_models
from app.services.template_service import (
    get_user_templates,
    get_template,
    create_template,
    update_template,
    delete_template,
)
from app.services.history_service import (
    get_user_history,
    get_history_entry,
    create_history_entry,
    delete_history_entry,
)

logger = logging.getLogger(__name__)
api_v1_bp = Blueprint('api_v1', __name__)


# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

@api_v1_bp.route('/config', methods=['GET'])
@login_required
def get_config():
    """Get current user configuration (no raw API keys exposed)."""
    providers = current_app.config.get('PROVIDERS', {})
    result = {}
    for pid, pinfo in providers.items():
        pc = ProviderConfig.query.filter_by(
            user_id=current_user.id, provider_id=pid
        ).first()
        result[pid] = {
            'name': pinfo['name'],
            'has_api_key': bool(pc and pc.api_key_encrypted),
            'selected_model': pc.selected_model if pc else pinfo.get('default_model', ''),
            'models': (pc.models_cache if pc else []) or [],
        }
    return jsonify({'providers': result})


@api_v1_bp.route('/config', methods=['POST'])
@login_required
def save_config():
    """Save provider configuration (API key and/or selected model)."""
    data = request.get_json(silent=True) or {}
    providers = current_app.config.get('PROVIDERS', {})

    provider_id = data.get('provider', '').strip()
    ok, err = validate_provider_id(provider_id, providers)
    if not ok:
        return jsonify({'error': err}), 400

    api_key = data.get('api_key', '').strip()
    model_id = data.get('model', '').strip()

    if api_key:
        ok, err = validate_api_key(api_key)
        if not ok:
            return jsonify({'error': err}), 400

    # Get or create provider config for this user
    pc = ProviderConfig.query.filter_by(
        user_id=current_user.id, provider_id=provider_id
    ).first()
    if not pc:
        pc = ProviderConfig(user_id=current_user.id, provider_id=provider_id)
        db.session.add(pc)

    if api_key:
        pc.api_key_encrypted = encrypt_api_key(api_key)
    if model_id:
        pc.selected_model = model_id

    db.session.commit()
    logger.info('Config saved: provider=%s user=%d', provider_id, current_user.id)

    return jsonify({
        'success': True,
        'message': 'Configuration sauvegardee',
        'has_api_key': bool(pc.api_key_encrypted),
        'selected_model': pc.selected_model,
    })


# -----------------------------------------------------------------------
# Provider Models
# -----------------------------------------------------------------------

@api_v1_bp.route('/providers/<provider_id>/models', methods=['GET'])
@login_required
def get_provider_models(provider_id: str):
    """Get cached models for a provider."""
    providers = current_app.config.get('PROVIDERS', {})
    ok, err = validate_provider_id(provider_id, providers)
    if not ok:
        return jsonify({'error': err}), 404

    pc = ProviderConfig.query.filter_by(
        user_id=current_user.id, provider_id=provider_id
    ).first()

    models = (pc.models_cache if pc else []) or []
    return jsonify({'models': models})


@api_v1_bp.route('/providers/<provider_id>/refresh', methods=['POST'])
@login_required
def refresh_provider_models(provider_id: str):
    """Refresh model list from provider API."""
    providers = current_app.config.get('PROVIDERS', {})
    ok, err = validate_provider_id(provider_id, providers)
    if not ok:
        return jsonify({'error': err}), 404

    pc = ProviderConfig.query.filter_by(
        user_id=current_user.id, provider_id=provider_id
    ).first()
    if not pc or not pc.api_key_encrypted:
        return jsonify({'error': f'Cle API manquante pour {providers[provider_id]["name"]}'}), 400

    api_key = decrypt_api_key(pc.api_key_encrypted)
    models, error = fetch_models(provider_id, api_key)
    if error:
        return jsonify({'error': error}), 400

    pc.models_cache = models
    db.session.commit()
    return jsonify({'success': True, 'models': models})


# -----------------------------------------------------------------------
# Templates
# -----------------------------------------------------------------------

@api_v1_bp.route('/templates', methods=['GET'])
@login_required
def list_templates():
    """List all templates for current user."""
    templates = get_user_templates(current_user.id)
    return jsonify({'templates': [t.to_dict() for t in templates]})


@api_v1_bp.route('/templates', methods=['POST'])
@login_required
def create_template_api():
    """Create a new template."""
    data = request.get_json(silent=True) or {}
    tpl, err = create_template(
        user_id=current_user.id,
        name=data.get('name', ''),
        content=data.get('content', ''),
        description=data.get('description', ''),
        default_provider=data.get('default_provider', 'zai'),
        default_model=data.get('default_model', 'glm-4.7'),
    )
    if err:
        return jsonify({'error': err}), 400
    return jsonify({'success': True, 'template': tpl.to_dict()}), 201


@api_v1_bp.route('/templates/<int:template_id>', methods=['PUT'])
@login_required
def update_template_api(template_id: int):
    """Update an existing template."""
    data = request.get_json(silent=True) or {}
    tpl, err = update_template(template_id, current_user.id, **data)
    if err:
        status = 404 if 'non trouve' in err else 400
        return jsonify({'error': err}), status
    return jsonify({'success': True, 'template': tpl.to_dict()})


@api_v1_bp.route('/templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_template_api(template_id: int):
    """Delete a template."""
    ok, err = delete_template(template_id, current_user.id)
    if not ok:
        return jsonify({'error': err}), 404
    return jsonify({'success': True, 'message': 'Template supprime'})


# -----------------------------------------------------------------------
# Generation
# -----------------------------------------------------------------------

def _prepare_generation(data: dict):
    """Shared validation for generate and generate/stream. Returns tuple or error response."""
    template_id = data.get('template_id')
    if not template_id:
        return None, (jsonify({'error': 'ID de template manquant'}), 400)

    tpl = get_template(int(template_id), current_user.id)
    if not tpl:
        return None, (jsonify({'error': 'Template non trouve'}), 404)

    variables = data.get('variables', {})
    expected_vars = extract_variables(tpl.content)
    ok, err = validate_variable_values(variables, expected_vars)
    if not ok:
        return None, (jsonify({'error': err}), 400)

    provider_id = data.get('provider') or tpl.default_provider or 'zai'
    model_id = data.get('model') or tpl.default_model or 'glm-4.7'

    providers = current_app.config.get('PROVIDERS', {})
    ok, err = validate_provider_id(provider_id, providers)
    if not ok:
        return None, (jsonify({'error': err}), 400)

    pc = ProviderConfig.query.filter_by(
        user_id=current_user.id, provider_id=provider_id
    ).first()
    if not pc or not pc.api_key_encrypted:
        return None, (jsonify({
            'error': f'Cle API manquante pour {providers[provider_id]["name"]}. '
                     f'Configurez-la dans le panneau de configuration.'
        }), 400)

    api_key = decrypt_api_key(pc.api_key_encrypted)
    prompt = safe_substitute(tpl.content, variables)

    return {
        'tpl': tpl,
        'variables': variables,
        'provider_id': provider_id,
        'model_id': model_id,
        'api_key': api_key,
        'prompt': prompt,
    }, None


@api_v1_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    """Generate result from template (synchronous)."""
    data = request.get_json(silent=True) or {}
    ctx, error_resp = _prepare_generation(data)
    if error_resp:
        return error_resp

    result, error = call_llm_api(
        ctx['prompt'], ctx['provider_id'], ctx['model_id'], ctx['api_key']
    )
    if error:
        return jsonify({'error': error}), 500

    entry = create_history_entry(
        user_id=current_user.id,
        template_id=ctx['tpl'].id,
        template_name=ctx['tpl'].name,
        variables=ctx['variables'],
        provider=ctx['provider_id'],
        model=ctx['model_id'],
        result=result,
    )
    return jsonify({'success': True, 'result': result, 'entry_id': entry.id})


@api_v1_bp.route('/generate/stream', methods=['POST'])
@login_required
def generate_stream():
    """Generate result with Server-Sent Events streaming."""
    data = request.get_json(silent=True) or {}
    ctx, error_resp = _prepare_generation(data)
    if error_resp:
        return error_resp

    tpl = ctx['tpl']
    variables = ctx['variables']
    provider_id = ctx['provider_id']
    model_id = ctx['model_id']
    user_id = current_user.id

    def event_stream():
        full_content = ''
        for event in stream_llm_api(ctx['prompt'], provider_id, model_id, ctx['api_key']):
            yield event
            # Capture final content for history
            if '"type": "done"' in event or '"type":"done"' in event:
                import json as _json
                try:
                    line = event.strip()
                    if line.startswith('data: '):
                        payload = _json.loads(line[6:])
                        full_content = payload.get('content', '')
                except Exception:
                    pass

        # Save to history after streaming completes
        if full_content:
            from app import db as _db
            entry = create_history_entry(
                user_id=user_id,
                template_id=tpl.id,
                template_name=tpl.name,
                variables=variables,
                provider=provider_id,
                model=model_id,
                result=full_content,
            )
            import json as _json
            yield f"data: {_json.dumps({'type': 'saved', 'entry_id': entry.id})}\n\n"

    return Response(event_stream(), mimetype='text/event-stream')


# -----------------------------------------------------------------------
# History
# -----------------------------------------------------------------------

@api_v1_bp.route('/history', methods=['GET'])
@login_required
def list_history():
    """Get paginated history with optional filters."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', None, type=int)
    template_id = request.args.get('template_id', None, type=int)
    provider = request.args.get('provider', None, type=str)
    search = request.args.get('search', None, type=str)

    result = get_user_history(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        template_id=template_id,
        provider=provider,
        search=search,
    )
    return jsonify(result)


@api_v1_bp.route('/history/<int:entry_id>', methods=['GET'])
@login_required
def get_history(entry_id: int):
    """Get a single history entry."""
    entry = get_history_entry(entry_id, current_user.id)
    if not entry:
        return jsonify({'error': 'Entree non trouvee'}), 404
    return jsonify({'entry': entry.to_dict()})


@api_v1_bp.route('/history/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_history(entry_id: int):
    """Delete a history entry."""
    ok, err = delete_history_entry(entry_id, current_user.id)
    if not ok:
        return jsonify({'error': err}), 404
    return jsonify({'success': True, 'message': 'Entree supprimee'})


@api_v1_bp.route('/export/<int:entry_id>', methods=['GET'])
@login_required
def export_entry(entry_id: int):
    """Export a history entry as markdown file download."""
    entry = get_history_entry(entry_id, current_user.id)
    if not entry:
        return jsonify({'error': 'Entree non trouvee'}), 404

    filename = f'generation_{entry.id}.md'
    content = entry.result or ''

    return Response(
        content,
        mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
