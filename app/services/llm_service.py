"""LLM Provider service - handles API calls with streaming support."""
import json
import logging
from typing import Optional, Tuple, Generator, Dict, Any

import requests as http_requests
from flask import current_app

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = '2023-06-01'

# Provider-specific parameters added to every OpenAI-format request
_PROVIDER_PARAMS: Dict[str, dict] = {
    'zai': {'thinking': {'type': 'disabled'}},
    'alibaba': {'thinking': {'type': 'disabled'}},
}

# Static model lists - used as fallback and merged with dynamic API results.
# Sorted alphabetically by name. 'api_format' defaults to 'openai' when absent.
#
# zai: liste officielle GLM Coding Plan (docs.z.ai/devpack, juin 2026) -
# exactement 5 modeles sur l'endpoint coding.
# alibaba: whitelist verifiee par appels reels sur coding-intl.dashscope.aliyuncs.com
# (10/06/2026) - IDs sensibles a la casse, pas d'endpoint GET /models.
# opencode: liste GET https://opencode.ai/zen/go/v1/models (18 modeles) -
# MiniMax/Qwen passent par /messages (format anthropic), le reste par /chat/completions.
_STATIC_MODELS: Dict[str, list] = {
    'zai': [
        {'id': 'glm-4.5-air', 'name': 'GLM-4.5-Air', 'description': 'Zhipu AI - leger et rapide, quota 1x'},
        {'id': 'glm-4.7', 'name': 'GLM-4.7', 'description': 'Zhipu AI - standard, quota 1x'},
        {'id': 'glm-5', 'name': 'GLM-5', 'description': 'Zhipu AI - generation precedente (744B MoE)'},
        {'id': 'glm-5-turbo', 'name': 'GLM-5-Turbo', 'description': 'Zhipu AI - variante rapide de GLM-5'},
        {'id': 'glm-5.1', 'name': 'GLM-5.1 (Recommande)', 'description': 'Zhipu AI - modele phare, 200K contexte'},
    ],
    'alibaba': [
        {'id': 'glm-4.7', 'name': 'GLM-4.7', 'description': 'Zhipu AI - modele tiers economique'},
        {'id': 'glm-5', 'name': 'GLM-5', 'description': 'Zhipu AI - modele tiers'},
        {'id': 'kimi-k2.5', 'name': 'Kimi K2.5', 'description': 'Moonshot AI - vision'},
        {'id': 'MiniMax-M2.5', 'name': 'MiniMax M2.5', 'description': 'MiniMax - casse exacte requise'},
        {'id': 'qwen3-coder-next', 'name': 'Qwen3-Coder-Next', 'description': 'Alibaba - coder next-gen'},
        {'id': 'qwen3-coder-plus', 'name': 'Qwen3-Coder-Plus', 'description': 'Alibaba - code agentique'},
        {'id': 'qwen3-max-2026-01-23', 'name': 'Qwen3-Max', 'description': 'Alibaba - capacite maximale (snapshot date)'},
        {'id': 'qwen3.5-plus', 'name': 'Qwen3.5-Plus', 'description': 'Alibaba - generation precedente, vision'},
        {'id': 'qwen3.6-plus', 'name': 'Qwen3.6-Plus', 'description': 'Alibaba - agentic coding, vision, 1M contexte'},
        {'id': 'qwen3.7-plus', 'name': 'Qwen3.7-Plus (Recommande)', 'description': 'Alibaba - derniere generation, vision, 1M contexte'},
    ],
    'opencode': [
        {'id': 'deepseek-v4-flash', 'name': 'DeepSeek V4 Flash', 'description': 'DeepSeek - rapide'},
        {'id': 'deepseek-v4-pro', 'name': 'DeepSeek V4 Pro', 'description': 'DeepSeek - haute capacite'},
        {'id': 'glm-5', 'name': 'GLM-5', 'description': 'Zhipu AI'},
        {'id': 'glm-5.1', 'name': 'GLM-5.1 (Recommande)', 'description': 'Zhipu AI - derniere generation'},
        {'id': 'hy3-preview', 'name': 'HY3 Preview', 'description': 'Hunyuan 3 - preview (non documente)'},
        {'id': 'kimi-k2.5', 'name': 'Kimi K2.5', 'description': 'Moonshot AI - vision'},
        {'id': 'kimi-k2.6', 'name': 'Kimi K2.6', 'description': 'Moonshot AI - derniere generation'},
        {'id': 'mimo-v2-omni', 'name': 'MiMo-V2 Omni', 'description': 'Xiaomi - multimodal (non documente)'},
        {'id': 'mimo-v2-pro', 'name': 'MiMo-V2 Pro', 'description': 'Xiaomi (non documente)'},
        {'id': 'mimo-v2.5', 'name': 'MiMo-V2.5', 'description': 'Xiaomi'},
        {'id': 'mimo-v2.5-pro', 'name': 'MiMo-V2.5-Pro', 'description': 'Xiaomi - haute capacite'},
        {'id': 'minimax-m2.5', 'name': 'MiniMax M2.5', 'description': 'MiniMax', 'api_format': 'anthropic'},
        {'id': 'minimax-m2.7', 'name': 'MiniMax M2.7', 'description': 'MiniMax', 'api_format': 'anthropic'},
        {'id': 'minimax-m3', 'name': 'MiniMax M3', 'description': 'MiniMax - derniere generation', 'api_format': 'anthropic'},
        {'id': 'qwen3.5-plus', 'name': 'Qwen3.5 Plus', 'description': 'Alibaba - generation precedente', 'api_format': 'anthropic'},
        {'id': 'qwen3.6-plus', 'name': 'Qwen3.6 Plus', 'description': 'Alibaba - 1M contexte', 'api_format': 'anthropic'},
        {'id': 'qwen3.7-max', 'name': 'Qwen3.7 Max', 'description': 'Alibaba - capacite maximale', 'api_format': 'anthropic'},
        {'id': 'qwen3.7-plus', 'name': 'Qwen3.7 Plus', 'description': 'Alibaba - derniere generation, 1M contexte', 'api_format': 'anthropic'},
    ],
}


def get_provider_info(provider_id: str) -> Optional[dict]:
    """Return provider definition from app config."""
    return current_app.config.get('PROVIDERS', {}).get(provider_id)


def get_static_models(provider_id: str) -> list:
    """Return a sorted copy of the static model list for a provider."""
    return _sort_models(list(_STATIC_MODELS.get(provider_id, [])))


def _model_api_format(provider_id: str, model_id: str) -> str:
    """Resolve the API format ('openai' or 'anthropic') for a model."""
    for m in _STATIC_MODELS.get(provider_id, []):
        if m.get('id') == model_id:
            return m.get('api_format', 'openai')
    # Heuristique pour les modeles OpenCode Go absents de la liste statique :
    # les familles MiniMax et Qwen passent par l'endpoint Anthropic /messages
    lowered = (model_id or '').lower()
    if provider_id == 'opencode' and (lowered.startswith('minimax') or lowered.startswith('qwen')):
        return 'anthropic'
    return 'openai'


def _build_request(
    provider: dict,
    provider_id: str,
    model_id: str,
    api_key: str,
    prompt: str,
    stream: bool,
) -> Tuple[str, dict, dict, str]:
    """Build (url, headers, payload, api_format) for a generation call."""
    api_format = _model_api_format(provider_id, model_id)

    # Un format anthropic exige un endpoint anthropic configure : sinon on retombe
    # explicitement sur le format openai plutot que d'envoyer un payload Anthropic
    # sur un endpoint chat/completions (erreurs provider indebuggables)
    if api_format == 'anthropic' and not provider.get('anthropic_url'):
        logger.warning(
            "Modele %s marque anthropic mais provider %s sans anthropic_url : format openai utilise",
            model_id, provider_id,
        )
        api_format = 'openai'

    if api_format == 'anthropic':
        url = provider['anthropic_url']
        headers = {
            'x-api-key': api_key,
            'anthropic-version': ANTHROPIC_VERSION,
            'Content-Type': 'application/json',
        }
        payload: Dict[str, Any] = {
            'model': model_id,
            'max_tokens': 8192,
            'temperature': 0.7,
            'top_p': 0.95,
            'messages': [{'role': 'user', 'content': prompt}],
        }
    else:
        url = provider['api_url']
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': model_id,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'max_tokens': 8192,
            'top_p': 0.95,
        }
        payload.update(_PROVIDER_PARAMS.get(provider_id, {}))

    if stream:
        payload['stream'] = True
    return url, headers, payload, api_format


def _extract_content(data: dict, api_format: str) -> str:
    """Extract assistant text from a non-streaming API response."""
    if api_format == 'anthropic':
        blocks = data.get('content') or []
        return ''.join(
            b.get('text', '') for b in blocks
            if isinstance(b, dict) and b.get('type') == 'text'
        )
    if 'choices' in data and data['choices']:
        msg = data['choices'][0].get('message', {})
        return msg.get('content', '') or msg.get('reasoning_content', '')
    return ''


def _http_error_details(exc: http_requests.exceptions.HTTPError) -> Tuple[str, int]:
    """Map an upstream HTTP error to (message, suggested API status code)."""
    status = exc.response.status_code if exc.response is not None else 0
    if status == 401:
        return "Cle API invalide ou expiree. Verifiez dans la configuration.", 400
    if status == 429:
        return "Trop de requetes. Patientez quelques instants.", 429
    if status >= 500:
        return "Erreur serveur du provider. Reessayez plus tard.", 502
    return f"Erreur HTTP {status}", 502


def call_llm_api(
    prompt: str,
    provider_id: str,
    model_id: str,
    api_key: str,
) -> Tuple[Optional[str], Optional[str], int]:
    """Call LLM API synchronously. Returns (result, error, status_code).

    status_code is the suggested HTTP status for the API response
    (200 on success, 4xx for user-correctable errors, 5xx otherwise).
    """
    provider = get_provider_info(provider_id)
    if not provider:
        return None, f"Provider inconnu : {provider_id}", 400
    if not api_key:
        return None, f"Cle API manquante pour {provider['name']}", 400

    url, headers, payload, api_format = _build_request(
        provider, provider_id, model_id, api_key, prompt, stream=False
    )

    try:
        logger.info('Calling %s model=%s format=%s', provider['name'], model_id, api_format)
        resp = http_requests.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()

        content = _extract_content(data, api_format)
        if content:
            logger.info('Success - %d chars', len(content))
            return content, None, 200
        if api_format == 'openai' and 'choices' not in data:
            return None, "Format de reponse invalide", 502
        return None, "Reponse vide du modele", 502

    except http_requests.exceptions.Timeout:
        return None, "Delai d'attente depasse (3 minutes). Reessayez.", 504
    except http_requests.exceptions.HTTPError as exc:
        message, status = _http_error_details(exc)
        return None, message, status
    except http_requests.exceptions.ConnectionError:
        return None, "Erreur de connexion. Verifiez votre acces internet.", 502
    except Exception as exc:
        logger.error('Unexpected LLM error: %s', exc, exc_info=True)
        return None, f"Erreur inattendue : {exc}", 500


def _stream_error(chunk: dict, api_format: str) -> Optional[str]:
    """Detect an upstream error event inside a streaming response (post-200)."""
    if api_format == 'anthropic':
        if chunk.get('type') == 'error':
            err = chunk.get('error') or {}
            return f"Erreur du provider : {err.get('message') or err.get('type') or 'inconnue'}"
        return None
    err = chunk.get('error')
    if isinstance(err, dict):
        return f"Erreur du provider : {err.get('message') or err.get('code') or 'inconnue'}"
    return None


def _stream_token(chunk: dict, api_format: str) -> str:
    """Extract a text token from a streaming event payload."""
    if api_format == 'anthropic':
        if chunk.get('type') == 'content_block_delta':
            delta = chunk.get('delta') or {}
            if delta.get('type') == 'text_delta':
                return delta.get('text', '') or ''
        return ''
    delta = chunk.get('choices', [{}])[0].get('delta', {})
    token = delta.get('content', '') or ''
    # Fallback to reasoning_content for thinking models
    if not token:
        token = delta.get('reasoning_content', '') or ''
    return token


def stream_llm_api(
    prompt: str,
    provider_id: str,
    model_id: str,
    api_key: str,
) -> Generator[str, None, None]:
    """Stream LLM response as Server-Sent Events."""
    provider = get_provider_info(provider_id)
    if not provider:
        yield _sse({'type': 'error', 'message': f'Provider inconnu : {provider_id}'})
        return
    if not api_key:
        yield _sse({'type': 'error', 'message': f'Cle API manquante pour {provider["name"]}'})
        return

    url, headers, payload, api_format = _build_request(
        provider, provider_id, model_id, api_key, prompt, stream=True
    )

    yield _sse({'type': 'start', 'message': 'Generation en cours...'})

    try:
        resp = http_requests.post(
            url, headers=headers, json=payload,
            stream=True, timeout=180,
        )
        resp.raise_for_status()

        full_content = ''
        for line in resp.iter_lines():
            if not line:
                continue
            decoded = line.decode('utf-8')
            if not decoded.startswith('data: '):
                continue
            data_str = decoded[6:].strip()
            if data_str == '[DONE]':
                break
            try:
                chunk = json.loads(data_str)
                if api_format == 'anthropic' and chunk.get('type') == 'message_stop':
                    break
                # Erreur upstream emise en cours de stream (apres le HTTP 200) :
                # la propager au client au lieu de terminer sur un faux 'done'
                upstream_error = _stream_error(chunk, api_format)
                if upstream_error:
                    logger.warning('Stream upstream error (%s): %s', provider_id, upstream_error)
                    yield _sse({'type': 'error', 'message': upstream_error})
                    return
                token = _stream_token(chunk, api_format)
                if token:
                    full_content += token
                    yield _sse({'type': 'token', 'content': token})
            except (json.JSONDecodeError, IndexError, KeyError):
                continue

        yield _sse({'type': 'done', 'content': full_content})

    except http_requests.exceptions.Timeout:
        yield _sse({'type': 'error', 'message': "Delai d'attente depasse"})
    except http_requests.exceptions.HTTPError as exc:
        message, _ = _http_error_details(exc)
        yield _sse({'type': 'error', 'message': message})
    except Exception as exc:
        logger.error('Stream error: %s', exc, exc_info=True)
        yield _sse({'type': 'error', 'message': str(exc)})


def _sort_models(models: list) -> list:
    """Sort models alphabetically by display name (fallback: id)."""
    return sorted(
        models,
        key=lambda m: (
            (m.get('name') or m.get('id') or '').lower(),
            (m.get('id') or '').lower(),
        ),
    )


def fetch_models(
    provider_id: str,
    api_key: str,
) -> Tuple[Optional[list], Optional[str]]:
    """Fetch available models. Tries dynamic API, then merges with static known models.

    Providers without a models_url (e.g. Alibaba Coding Plan, no GET /models
    endpoint) use the static list directly. Result is sorted alphabetically by name.
    """
    provider = get_provider_info(provider_id)
    if not provider:
        return None, f"Provider inconnu : {provider_id}"
    if not api_key:
        return None, f"Cle API manquante pour {provider['name']}"

    static = _STATIC_MODELS.get(provider_id, [])
    dynamic: list = []
    fetch_error: Optional[str] = None

    # Attempt dynamic fetch from provider API (skipped when no models endpoint exists)
    if provider.get('models_url'):
        try:
            resp = http_requests.get(
                provider['models_url'],
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for m in data.get('data', []):
                info: Dict[str, Any] = {
                    'id': m.get('id'),
                    'name': m.get('name', m.get('id', '')),
                    'description': m.get('description', m.get('object', '')),
                }
                if provider_id == 'openrouter':
                    info['context_length'] = m.get('context_length', 0)
                    info['pricing'] = m.get('pricing', {})
                dynamic.append(info)

        except http_requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            fetch_error = ("Cle API invalide" if status == 401
                           else "Trop de requetes" if status == 429
                           else f"Erreur HTTP {status}")
        except http_requests.exceptions.ConnectionError:
            fetch_error = "Erreur de connexion"
        except http_requests.exceptions.Timeout:
            fetch_error = "Delai d'attente depasse"
        except Exception as exc:
            logger.error('Fetch models error: %s', exc, exc_info=True)
            fetch_error = f"Erreur : {exc}"

    # Merge dynamic + static : les metadonnees statiques (nom lisible, description,
    # api_format) priment sur les entrees dynamiques brutes du meme id
    if dynamic:
        by_id: Dict[str, dict] = {m['id']: m for m in dynamic if m.get('id')}
        for s in static:
            if s['id'] in by_id:
                by_id[s['id']] = {**by_id[s['id']], **s}
            else:
                by_id[s['id']] = dict(s)
        return _sort_models(list(by_id.values())), None

    # Dynamic failed, empty or unavailable - use static fallback
    if static:
        if fetch_error:
            logger.warning('Dynamic fetch failed for %s (%s), using static list', provider_id, fetch_error)
        return _sort_models(list(static)), None

    # No static fallback available - return the error
    return None, fetch_error or "Aucun modele disponible"


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
