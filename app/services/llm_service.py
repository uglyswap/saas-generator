"""LLM Provider service - handles API calls with streaming support."""
import json
import logging
from typing import Optional, Tuple, Generator, Dict, Any

import requests as http_requests
from flask import current_app

logger = logging.getLogger(__name__)

# Provider-specific parameters added to every request
_PROVIDER_PARAMS: Dict[str, dict] = {
    'zai': {'thinking': {'type': 'disabled'}},
}

# Static model lists for providers that don't expose a /models endpoint
_STATIC_MODELS: Dict[str, list] = {
    'alibaba': [
        {'id': 'kimi-k2.5', 'name': 'Kimi K2.5 (Recommended)', 'description': 'Moonshot AI - vision capable'},
        {'id': 'qwen3.5-plus', 'name': 'Qwen 3.5 Plus (Recommended)', 'description': 'Alibaba - vision capable'},
        {'id': 'glm-5', 'name': 'GLM-5 (Recommended)', 'description': 'Zhipu AI'},
        {'id': 'MiniMax-M2.5', 'name': 'MiniMax M2.5 (Recommended)', 'description': 'MiniMax'},
        {'id': 'qwen3-coder-plus', 'name': 'Qwen 3 Coder Plus', 'description': 'Alibaba - coding specialist'},
        {'id': 'qwen3-coder-next', 'name': 'Qwen 3 Coder Next', 'description': 'Alibaba - next-gen coding'},
        {'id': 'qwen3-max-2026-01-23', 'name': 'Qwen 3 Max', 'description': 'Alibaba - max capability'},
        {'id': 'glm-4.7', 'name': 'GLM-4.7', 'description': 'Zhipu AI'},
    ],
}


def get_provider_info(provider_id: str) -> Optional[dict]:
    """Return provider definition from app config."""
    return current_app.config.get('PROVIDERS', {}).get(provider_id)


def call_llm_api(
    prompt: str,
    provider_id: str,
    model_id: str,
    api_key: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Call LLM API synchronously. Returns (result, error)."""
    provider = get_provider_info(provider_id)
    if not provider:
        return None, f"Provider inconnu : {provider_id}"
    if not api_key:
        return None, f"Cle API manquante pour {provider['name']}"

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload: Dict[str, Any] = {
        'model': model_id,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.7,
        'max_tokens': 8192,
        'top_p': 0.95,
    }
    payload.update(_PROVIDER_PARAMS.get(provider_id, {}))

    try:
        logger.info('Calling %s model=%s', provider['name'], model_id)
        resp = http_requests.post(
            provider['api_url'], headers=headers, json=payload, timeout=180
        )
        resp.raise_for_status()
        data = resp.json()

        if 'choices' in data and data['choices']:
            msg = data['choices'][0].get('message', {})
            content = msg.get('content', '') or msg.get('reasoning_content', '')
            if content:
                logger.info('Success - %d chars', len(content))
                return content, None
            return None, "Reponse vide du modele"
        return None, "Format de reponse invalide"

    except http_requests.exceptions.Timeout:
        return None, "Delai d'attente depasse (3 minutes). Reessayez."
    except http_requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status == 401:
            return None, "Cle API invalide ou expiree. Verifiez dans la configuration."
        if status == 429:
            return None, "Trop de requetes. Patientez quelques instants."
        if status >= 500:
            return None, "Erreur serveur du provider. Reessayez plus tard."
        return None, f"Erreur HTTP {status}"
    except http_requests.exceptions.ConnectionError:
        return None, "Erreur de connexion. Verifiez votre acces internet."
    except Exception as exc:
        logger.error('Unexpected LLM error: %s', exc, exc_info=True)
        return None, f"Erreur inattendue : {exc}"


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

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload: Dict[str, Any] = {
        'model': model_id,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.7,
        'max_tokens': 8192,
        'top_p': 0.95,
        'stream': True,
    }
    payload.update(_PROVIDER_PARAMS.get(provider_id, {}))

    yield _sse({'type': 'start', 'message': 'Generation en cours...'})

    try:
        resp = http_requests.post(
            provider['api_url'], headers=headers, json=payload,
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
                delta = chunk.get('choices', [{}])[0].get('delta', {})
                token = delta.get('content', '')
                if token:
                    full_content += token
                    yield _sse({'type': 'token', 'content': token})
            except (json.JSONDecodeError, IndexError, KeyError):
                continue

        yield _sse({'type': 'done', 'content': full_content})

    except http_requests.exceptions.Timeout:
        yield _sse({'type': 'error', 'message': "Delai d'attente depasse"})
    except http_requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        msg = "Cle API invalide" if status == 401 else f"Erreur HTTP {status}"
        yield _sse({'type': 'error', 'message': msg})
    except Exception as exc:
        logger.error('Stream error: %s', exc, exc_info=True)
        yield _sse({'type': 'error', 'message': str(exc)})


def fetch_models(
    provider_id: str,
    api_key: str,
) -> Tuple[Optional[list], Optional[str]]:
    """Fetch available models from a provider API."""
    provider = get_provider_info(provider_id)
    if not provider:
        return None, f"Provider inconnu : {provider_id}"
    if not api_key:
        return None, f"Cle API manquante pour {provider['name']}"

    # Some providers (e.g. Alibaba Coding Plan) don't expose a /models endpoint.
    # Return the static model list if available.
    if provider_id in _STATIC_MODELS:
        return list(_STATIC_MODELS[provider_id]), None

    try:
        resp = http_requests.get(
            provider['models_url'],
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        models = []
        for m in data.get('data', []):
            info: Dict[str, Any] = {
                'id': m.get('id'),
                'name': m.get('name', m.get('id', '')),
                'description': m.get('description', m.get('object', '')),
            }
            if provider_id == 'openrouter':
                info['context_length'] = m.get('context_length', 0)
                info['pricing'] = m.get('pricing', {})
            models.append(info)

        models.sort(key=lambda x: (x.get('id') or '').lower())
        return models, None

    except http_requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status == 401:
            return None, "Cle API invalide"
        if status == 429:
            return None, "Trop de requetes"
        return None, f"Erreur HTTP {status}"
    except http_requests.exceptions.ConnectionError:
        return None, "Erreur de connexion"
    except http_requests.exceptions.Timeout:
        return None, "Delai d'attente depasse"
    except Exception as exc:
        logger.error('Fetch models error: %s', exc, exc_info=True)
        return None, f"Erreur : {exc}"


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
