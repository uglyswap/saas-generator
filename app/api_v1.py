"""API v1 blueprint - RESTful endpoints for templates, generation, history, config, export, versioning."""
import logging
from flask import Blueprint, request, jsonify, Response, current_app
from flask_login import login_required, current_user

from app import db, limiter
from app.models import ProviderConfig, Template, ExportTemplate, User
from app.services.config_service import get_user_default, get_provider_model_for_user
from app.utils.security import encrypt_api_key, decrypt_api_key
from app.utils.validators import (
    validate_api_key,
    validate_provider_id,
    validate_variable_values,
    safe_substitute,
    extract_variables,
)
from app.services.llm_service import (
    call_llm_api,
    call_llm_api_full,
    stream_llm_api,
    fetch_models,
    get_static_models,
)

# Marqueur persistant ajoute a un resultat tronque : sans lui, un document coupe
# par max_tokens serait relu/exporte plus tard comme s'il etait complet.
TRUNCATION_MARKER = ('\n\n> **Avertissement : reponse tronquee, '
                     'limite de tokens atteinte (LLM_MAX_TOKENS).**')
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
    update_history_result,
    delete_history_entry,
    get_entry_versions,
    get_version,
    restore_version,
)
from app.services.export_service import (
    export_markdown,
    export_html,
    export_pdf,
    export_docx,
)

logger = logging.getLogger(__name__)
api_v1_bp = Blueprint('api_v1', __name__)


def _as_str(value, default: str = '') -> str:
    """Coerce a JSON value to a stripped string ('' when absent or wrong type)."""
    if isinstance(value, str):
        return value.strip()
    return default


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

    provider_id = _as_str(data.get('provider'))
    ok, err = validate_provider_id(provider_id, providers)
    if not ok:
        return jsonify({'error': err}), 400

    api_key = _as_str(data.get('api_key'))
    model_id = _as_str(data.get('model'))

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
        try:
            pc.api_key_encrypted = encrypt_api_key(api_key)
        except ValueError as exc:
            # Chiffrement impossible (ENCRYPTION_KEY mal formee) : ne pas persister
            # une cle vide silencieusement, remonter l'erreur a l'utilisateur
            db.session.rollback()
            return jsonify({'error': str(exc)}), 500
    if model_id:
        pc.selected_model = model_id
        # When saving a model choice, mark this provider as the user's default
        current_user.default_provider = provider_id

    db.session.commit()
    logger.info('Config saved: provider=%s user=%d', provider_id, current_user.id)

    return jsonify({
        'success': True,
        'message': 'Configuration sauvegardee',
        'has_api_key': bool(pc.api_key_encrypted),
        'selected_model': pc.selected_model,
    })


# -----------------------------------------------------------------------
# Meta-Prompt Configuration (Template Generation AI)
# -----------------------------------------------------------------------

@api_v1_bp.route('/config/meta-prompt', methods=['GET'])
@login_required
def get_meta_prompt_config():
    """Get meta-prompt configuration for template content generation."""
    user = db.session.get(User, current_user.id)
    default_meta = current_app.config.get('DEFAULT_META_PROMPT', '')
    return jsonify({
        'meta_prompt': user.meta_prompt or default_meta,
        'provider': user.meta_prompt_provider or user.default_provider or '',
        'model': user.meta_prompt_model or '',
        'is_default': not bool(user.meta_prompt),
    })


@api_v1_bp.route('/config/meta-prompt', methods=['POST'])
@login_required
def save_meta_prompt_config():
    """Save meta-prompt configuration."""
    data = request.get_json(silent=True) or {}

    meta_prompt = _as_str(data.get('meta_prompt'))
    provider_id = _as_str(data.get('provider'))
    model_id = _as_str(data.get('model'))

    if meta_prompt and len(meta_prompt) > 50000:
        return jsonify({'error': 'Le meta-prompt est trop long (max 50000 caracteres)'}), 400

    if provider_id:
        providers = current_app.config.get('PROVIDERS', {})
        ok, err = validate_provider_id(provider_id, providers)
        if not ok:
            return jsonify({'error': err}), 400

    user = db.session.get(User, current_user.id)
    user.meta_prompt = meta_prompt
    if provider_id:
        user.meta_prompt_provider = provider_id
    if model_id:
        user.meta_prompt_model = model_id

    db.session.commit()
    logger.info('Meta-prompt config saved: user=%d', current_user.id)
    return jsonify({'success': True, 'message': 'Configuration du meta-prompt sauvegardee'})


@api_v1_bp.route('/generate/template-content', methods=['POST'])
@login_required
@limiter.limit('30 per minute')
def generate_template_content():
    """Generate template content using the meta-prompt and AI."""
    data = request.get_json(silent=True) or {}

    template_name = _as_str(data.get('name'))
    template_description = _as_str(data.get('description'))

    if not template_name:
        return jsonify({'error': 'Le nom du template est requis'}), 400
    if not template_description:
        return jsonify({'error': 'La description du template est requise'}), 400

    # Get meta-prompt config
    user = db.session.get(User, current_user.id)
    meta_prompt_text = user.meta_prompt or current_app.config.get('DEFAULT_META_PROMPT', '')

    if not meta_prompt_text:
        return jsonify({'error': 'Aucun meta-prompt configure'}), 400

    # Determine provider and model (meme chaine de fallback que la generation)
    provider_id = user.meta_prompt_provider or user.default_provider or ''
    if not provider_id:
        provider_id = get_user_default(current_user.id)[0] or ''
    model_id = user.meta_prompt_model or ''

    if not provider_id:
        return jsonify({'error': 'Aucun provider configure pour la generation de templates. '
                       'Configurez-le dans le panneau de configuration (Etape 4).'}), 400

    providers = current_app.config.get('PROVIDERS', {})
    ok, err = validate_provider_id(provider_id, providers)
    if not ok:
        return jsonify({'error': err}), 400

    # Get API key
    pc = ProviderConfig.query.filter_by(
        user_id=current_user.id, provider_id=provider_id
    ).first()
    if not pc or not pc.api_key_encrypted:
        return jsonify({
            'error': f'Cle API manquante pour {providers[provider_id]["name"]}. '
                     f'Configurez-la dans le panneau de configuration.'
        }), 400

    # Fallback model
    if not model_id:
        model_id = get_provider_model_for_user(current_user.id, provider_id)
    if not model_id:
        return jsonify({'error': 'Aucun modele configure'}), 400

    api_key = decrypt_api_key(pc.api_key_encrypted)

    # Substitute variables into meta-prompt
    prompt = safe_substitute(meta_prompt_text, {
        'nom_template': template_name,
        'description_template': template_description,
    })

    # Call LLM (synchronous - template content is short)
    result, error, status = call_llm_api(prompt, provider_id, model_id, api_key)
    if error:
        return jsonify({'error': error}), status

    return jsonify({'success': True, 'content': result})


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

    # Provider sans endpoint /models (ex. Alibaba Coding Plan) : la liste statique
    # embarquee fait foi, un cache perime ne doit pas la masquer
    if not providers[provider_id].get('models_url'):
        return jsonify({'models': get_static_models(provider_id)})

    # Cache utilisateur, sinon liste statique embarquee (premier usage d'un provider)
    models = (pc.models_cache if pc else []) or get_static_models(provider_id)
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
    """Create a new template. Provider/model are optional per-template overrides."""
    data = request.get_json(silent=True) or {}

    default_provider = _as_str(data.get('default_provider'))
    if default_provider:
        ok, err = validate_provider_id(default_provider, current_app.config.get('PROVIDERS', {}))
        if not ok:
            return jsonify({'error': err}), 400

    tpl, err = create_template(
        user_id=current_user.id,
        name=_as_str(data.get('name')),
        content=_as_str(data.get('content')),
        description=_as_str(data.get('description')),
        default_provider=default_provider,
        default_model=_as_str(data.get('default_model')),
    )
    if err:
        return jsonify({'error': err}), 400
    return jsonify({'success': True, 'template': tpl.to_dict()}), 201


# Champs modifiables d'un template : seules ces cles sont transmises au service
# (jamais **data brut, qui permettrait d'ecraser template_id/user_id)
_TEMPLATE_UPDATE_FIELDS = ('name', 'content', 'description', 'default_provider', 'default_model')


@api_v1_bp.route('/templates/<int:template_id>', methods=['PUT'])
@login_required
def update_template_api(template_id: int):
    """Update an existing template."""
    data = request.get_json(silent=True) or {}

    fields = {}
    for key in _TEMPLATE_UPDATE_FIELDS:
        if key in data:
            value = data[key]
            if value is not None and not isinstance(value, str):
                return jsonify({'error': f'Champ {key} invalide : chaine attendue'}), 400
            fields[key] = value or ''

    if fields.get('default_provider'):
        ok, err = validate_provider_id(fields['default_provider'].strip(), current_app.config.get('PROVIDERS', {}))
        if not ok:
            return jsonify({'error': err}), 400

    tpl, err = update_template(template_id, current_user.id, **fields)
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
    raw_template_id = data.get('template_id')
    if raw_template_id is None or raw_template_id == '':
        return None, (jsonify({'error': 'ID de template manquant'}), 400)
    try:
        template_id = int(raw_template_id)
    except (TypeError, ValueError):
        return None, (jsonify({'error': 'ID de template invalide'}), 400)

    tpl = get_template(template_id, current_user.id)
    if not tpl:
        return None, (jsonify({'error': 'Template non trouve'}), 404)

    variables = data.get('variables', {})
    expected_vars = extract_variables(tpl.content)
    ok, err = validate_variable_values(variables, expected_vars)
    if not ok:
        return None, (jsonify({'error': err}), 400)

    # Resolution du couple (provider, modele) :
    # 1. choix explicite de la requete
    # 2. override du template (s'il en a un)
    # 3. defaut general de l'utilisateur
    # Le modele du template n'est repris que si le provider resolu correspond
    # au provider du template (sinon on enverrait un modele au mauvais provider).
    provider_id = _as_str(data.get('provider')) or tpl.default_provider or ''
    model_id = _as_str(data.get('model'))
    if not model_id and tpl.default_model and tpl.default_provider and provider_id == tpl.default_provider:
        model_id = tpl.default_model

    if not provider_id:
        # Le modele du defaut general sera resolu plus bas par
        # get_provider_model_for_user (meme logique, une seule source)
        provider_id = get_user_default(current_user.id)[0] or ''

    if not provider_id:
        return None, (jsonify({
            'error': "Aucun provider configure. Choisissez un provider et un modele "
                     "par defaut dans le panneau Configuration."
        }), 400)

    providers = current_app.config.get('PROVIDERS', {})
    ok, err = validate_provider_id(provider_id, providers)
    if not ok:
        return None, (jsonify({'error': err}), 400)

    if not model_id:
        model_id = get_provider_model_for_user(current_user.id, provider_id)
    if not model_id:
        return None, (jsonify({'error': 'Aucun modele configure pour ce provider'}), 400)

    pc = ProviderConfig.query.filter_by(
        user_id=current_user.id, provider_id=provider_id
    ).first()
    if not pc or not pc.api_key_encrypted:
        return None, (jsonify({
            'error': f'Cle API manquante pour {providers[provider_id]["name"]}. '
                     f'Configurez-la dans le panneau de configuration.'
        }), 400)

    api_key = decrypt_api_key(pc.api_key_encrypted)
    if not api_key:
        # Valeur chiffree presente mais indechiffrable : SECRET_KEY/ENCRYPTION_KEY a change
        return None, (jsonify({
            'error': f'Cle API illisible pour {providers[provider_id]["name"]} '
                     f'(cle de chiffrement modifiee ?). Re-saisissez votre cle API.'
        }), 400)
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
@limiter.limit('30 per minute')
def generate():
    """Generate result from template (synchronous)."""
    data = request.get_json(silent=True) or {}
    ctx, error_resp = _prepare_generation(data)
    if error_resp:
        return error_resp

    result, truncated, error, status = call_llm_api_full(
        ctx['prompt'], ctx['provider_id'], ctx['model_id'], ctx['api_key']
    )
    if error:
        return jsonify({'error': error}), status

    # Meme traitement que la voie streaming : marqueur persistant + flag client,
    # pour qu'un document tronque ne soit pas relu/exporte comme s'il etait complet
    if truncated:
        result = (result or '') + TRUNCATION_MARKER

    entry = create_history_entry(
        user_id=current_user.id,
        template_id=ctx['tpl'].id,
        template_name=ctx['tpl'].name,
        variables=ctx['variables'],
        provider=ctx['provider_id'],
        model=ctx['model_id'],
        result=result,
    )
    return jsonify({'success': True, 'result': result, 'entry_id': entry.id, 'truncated': truncated})


@api_v1_bp.route('/generate/stream', methods=['POST'])
@login_required
@limiter.limit('30 per minute')
def generate_stream():
    """Generate result with Server-Sent Events streaming."""
    import json as _json
    data = request.get_json(silent=True) or {}
    ctx, error_resp = _prepare_generation(data)
    if error_resp:
        # Return error as SSE so the client can parse it
        try:
            err_data = _json.loads(error_resp[0].get_data(as_text=True))
            err_msg = err_data.get('error', 'Erreur inconnue')
        except Exception:
            err_msg = 'Erreur inconnue'
        def error_stream():
            yield f"data: {_json.dumps({'type': 'error', 'message': err_msg}, ensure_ascii=False)}\n\n"
        return Response(error_stream(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        })

    tpl_id = ctx['tpl'].id
    tpl_name = ctx['tpl'].name
    variables = ctx['variables']
    provider_id = ctx['provider_id']
    model_id = ctx['model_id']
    user_id = current_user.id
    prompt = ctx['prompt']
    api_key = ctx['api_key']
    # Reprise manuelle apres troncature : le client renvoie le document deja recu,
    # le service le reinjecte comme contexte assistant pour continuer la generation
    continue_from = _as_str(data.get('continue_from'))
    app = current_app._get_current_object()

    def event_stream():
        with app.app_context():
            full_content = ''
            truncated = False
            for event in stream_llm_api(prompt, provider_id, model_id, api_key,
                                        continue_from=continue_from):
                yield event
                if '"type": "done"' in event or '"type":"done"' in event:
                    try:
                        line = event.strip()
                        if line.startswith('data: '):
                            payload = _json.loads(line[6:])
                            full_content = payload.get('content', '')
                            truncated = bool(payload.get('truncated'))
                    except Exception:
                        pass

            # Save to history after streaming completes. Protege : une erreur DB
            # apres le 'done' ne doit pas casser le flux SSE sans explication
            if full_content:
                # Marqueur persistant (cf. TRUNCATION_MARKER) : un document tronque
                # ne doit pas etre relu/exporte plus tard comme s'il etait complet
                if truncated:
                    full_content += TRUNCATION_MARKER
                try:
                    entry = create_history_entry(
                        user_id=user_id,
                        template_id=tpl_id,
                        template_name=tpl_name,
                        variables=variables,
                        provider=provider_id,
                        model=model_id,
                        result=full_content,
                    )
                    yield f"data: {_json.dumps({'type': 'saved', 'entry_id': entry.id})}\n\n"
                except Exception as exc:
                    logger.error('History save failed after stream: %s', exc, exc_info=True)
                    yield ("data: " + _json.dumps({
                        'type': 'error',
                        'message': "Resultat genere mais non sauvegarde dans l'historique "
                                   "(erreur interne). Copiez-le avant de fermer.",
                    }, ensure_ascii=False) + "\n\n")

    return Response(event_stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive',
    })


# -----------------------------------------------------------------------
# Partial Regeneration (Phase 4)
# -----------------------------------------------------------------------

@api_v1_bp.route('/generate/partial', methods=['POST'])
@login_required
@limiter.limit('30 per minute')
def generate_partial():
    """Regenerate a selected section of text."""
    data = request.get_json(silent=True) or {}
    selected_text = _as_str(data.get('selected_text'))
    full_context = _as_str(data.get('full_context'))
    template_id = data.get('template_id')
    provider_id = _as_str(data.get('provider'))
    model_id = _as_str(data.get('model'))

    if not selected_text:
        return jsonify({'error': 'Aucun texte selectionne'}), 400
    if not provider_id or not model_id:
        return jsonify({'error': 'Provider et modele requis'}), 400

    providers = current_app.config.get('PROVIDERS', {})
    ok, err = validate_provider_id(provider_id, providers)
    if not ok:
        return jsonify({'error': err}), 400

    pc = ProviderConfig.query.filter_by(
        user_id=current_user.id, provider_id=provider_id
    ).first()
    if not pc or not pc.api_key_encrypted:
        return jsonify({'error': 'Cle API manquante'}), 400

    api_key = decrypt_api_key(pc.api_key_encrypted)

    prompt = (
        f"Voici le contexte complet d'un document :\n\n{full_context}\n\n"
        f"---\n\n"
        f"Reecris UNIQUEMENT la section suivante, en l'ameliorant tout en gardant "
        f"le meme style, ton et format que le reste du document. "
        f"Retourne UNIQUEMENT le texte de remplacement, sans explication :\n\n"
        f"{selected_text}"
    )

    result, truncated, error, status = call_llm_api_full(prompt, provider_id, model_id, api_key)
    if error:
        return jsonify({'error': error}), status

    # truncated remonte au client : le frontend refuse le remplacement automatique
    # d'une section par une version coupee (cf. app.js applyPartialRegeneration)
    return jsonify({'success': True, 'replacement': result, 'truncated': truncated})


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


@api_v1_bp.route('/history/<int:entry_id>', methods=['PATCH'])
@login_required
def patch_history(entry_id: int):
    """Update a history entry's result (edit mode)."""
    data = request.get_json(silent=True) or {}
    new_result = data.get('result')
    if new_result is None:
        return jsonify({'error': 'Champ result requis'}), 400

    entry, err = update_history_result(entry_id, current_user.id, new_result)
    if err:
        return jsonify({'error': err}), 404
    return jsonify({'success': True, 'entry': entry.to_dict()})


@api_v1_bp.route('/history/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_history(entry_id: int):
    """Delete a history entry."""
    ok, err = delete_history_entry(entry_id, current_user.id)
    if not ok:
        return jsonify({'error': err}), 404
    return jsonify({'success': True, 'message': 'Entree supprimee'})


# -----------------------------------------------------------------------
# Versioning (Phase 6)
# -----------------------------------------------------------------------

@api_v1_bp.route('/history/<int:entry_id>/versions', methods=['GET'])
@login_required
def list_versions(entry_id: int):
    """List all versions for a history entry."""
    versions = get_entry_versions(entry_id, current_user.id)
    if versions is None:
        return jsonify({'error': 'Entree non trouvee'}), 404
    return jsonify({'versions': versions})


@api_v1_bp.route('/history/<int:entry_id>/versions/<int:version_num>', methods=['GET'])
@login_required
def get_version_api(entry_id: int, version_num: int):
    """Get a specific version."""
    version = get_version(entry_id, current_user.id, version_num)
    if version is None:
        return jsonify({'error': 'Version non trouvee'}), 404
    return jsonify({'version': version})


@api_v1_bp.route('/history/<int:entry_id>/versions/<int:version_num>/restore', methods=['POST'])
@login_required
def restore_version_api(entry_id: int, version_num: int):
    """Restore a specific version."""
    result, err = restore_version(entry_id, current_user.id, version_num)
    if err:
        return jsonify({'error': err}), 404
    return jsonify({'success': True, 'result': result})


# -----------------------------------------------------------------------
# Export (Phase 2 - Multi-format)
# -----------------------------------------------------------------------

@api_v1_bp.route('/export/<int:entry_id>', methods=['GET'])
@login_required
def export_entry(entry_id: int):
    """Export a history entry in various formats (md, html, docx, pdf)."""
    entry = get_history_entry(entry_id, current_user.id)
    if not entry:
        return jsonify({'error': 'Entree non trouvee'}), 404

    fmt = request.args.get('format', 'md').lower()
    title = entry.template_name or 'Export'
    raw = entry.result or ''

    # Check if a branding template is specified
    template_id = request.args.get('template_id', None, type=int)
    header_text = ''
    footer_text = ''
    primary_color = '#2563eb'

    if template_id:
        export_tpl = ExportTemplate.query.filter_by(
            id=template_id, user_id=current_user.id
        ).first()
        if export_tpl:
            header_text = export_tpl.header_text or ''
            footer_text = export_tpl.footer_text or ''
            primary_color = export_tpl.primary_color or '#2563eb'

    try:
        if fmt == 'html':
            content, filename, mimetype = export_html(raw, title, header_text, footer_text, primary_color)
        elif fmt == 'pdf':
            content, filename, mimetype = export_pdf(raw, title, header_text, footer_text, primary_color)
        elif fmt == 'docx':
            content, filename, mimetype = export_docx(raw, title, header_text, footer_text, primary_color)
        else:  # md
            content, filename, mimetype = export_markdown(raw, title)
    except Exception as e:
        logger.error('Export failed: %s', e)
        return jsonify({'error': f'Erreur lors de l\'export: {str(e)}'}), 500

    return Response(
        content,
        mimetype=mimetype,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


# -----------------------------------------------------------------------
# Export Templates / Branding (Phase 5)
# -----------------------------------------------------------------------

@api_v1_bp.route('/export-templates', methods=['GET'])
@login_required
def list_export_templates():
    """List all export templates for current user."""
    templates = ExportTemplate.query.filter_by(user_id=current_user.id).order_by(
        ExportTemplate.created_at.desc()
    ).all()
    return jsonify({'templates': [t.to_dict() for t in templates]})


@api_v1_bp.route('/export-templates', methods=['POST'])
@login_required
def create_export_template():
    """Create a new export template."""
    data = request.get_json(silent=True) or {}
    name = _as_str(data.get('name'))
    if not name:
        return jsonify({'error': 'Nom requis'}), 400

    tpl = ExportTemplate(
        user_id=current_user.id,
        name=name,
        header_text=_as_str(data.get('header_text')),
        footer_text=_as_str(data.get('footer_text')),
        primary_color=_as_str(data.get('primary_color')) or '#2563eb',
    )
    db.session.add(tpl)
    db.session.commit()
    return jsonify({'success': True, 'template': tpl.to_dict()}), 201


@api_v1_bp.route('/export-templates/<int:tpl_id>', methods=['PUT'])
@login_required
def update_export_template(tpl_id: int):
    """Update an export template."""
    tpl = ExportTemplate.query.filter_by(id=tpl_id, user_id=current_user.id).first()
    if not tpl:
        return jsonify({'error': 'Template non trouve'}), 404

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        new_name = _as_str(data['name'])
        if not new_name:
            return jsonify({'error': 'Nom invalide'}), 400
        tpl.name = new_name
    if 'header_text' in data:
        tpl.header_text = _as_str(data['header_text'])
    if 'footer_text' in data:
        tpl.footer_text = _as_str(data['footer_text'])
    if 'primary_color' in data:
        tpl.primary_color = _as_str(data['primary_color']) or '#2563eb'

    db.session.commit()
    return jsonify({'success': True, 'template': tpl.to_dict()})


@api_v1_bp.route('/export-templates/<int:tpl_id>', methods=['DELETE'])
@login_required
def delete_export_template(tpl_id: int):
    """Delete an export template."""
    tpl = ExportTemplate.query.filter_by(id=tpl_id, user_id=current_user.id).first()
    if not tpl:
        return jsonify({'error': 'Template non trouve'}), 404
    db.session.delete(tpl)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Template supprime'})
