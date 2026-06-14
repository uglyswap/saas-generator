"""LLM Provider service - handles API calls with streaming support."""
import json
import logging
from typing import Optional, Tuple, Generator, Dict, Any

import requests as http_requests
from flask import current_app

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = '2023-06-01'
# Timeout de connexion : court (le provider doit accepter la connexion vite)
CONNECT_TIMEOUT = 15


def _request_timeout() -> tuple:
    """(connect, read) : le read s'applique entre deux chunks, pas au stream entier."""
    return (CONNECT_TIMEOUT, int(current_app.config.get('LLM_REQUEST_TIMEOUT', 300)))


# Plafond de sortie (max_tokens) par requete et par provider. ESTIMATIONS A
# CONFIRMER en doc provider (docs.z.ai, dashscope coding-intl, opencode.ai/zen/go) :
# un cap trop bas bride inutilement, trop haut laisse passer un 400 (rattrape par
# _http_error_details + l'auto-continuation). None = pas de clamp.
_PROVIDER_OUTPUT_CAP: Dict[str, Optional[int]] = {
    'zai': 16384,
    'alibaba': 32768,
    'opencode': 32768,
    'openrouter': None,
}

# Nombre maximum de relances automatiques apres une coupure a max_tokens.
MAX_CONTINUATIONS = 4
# Consigne de reprise envoyee au modele apres une troncature.
CONTINUE_HINT = (
    "Continue exactement la ou tu t'es arrete, au caractere suivant, sans repeter "
    "ni reformuler ce qui precede, sans introduction ni conclusion."
)


def _max_tokens(provider_id: Optional[str] = None) -> int:
    """Budget de sortie demande, clampe au plafond reel connu du provider.

    LLM_MAX_TOKENS est envoye tel quel comme max_tokens : au-dela du plafond d'un
    provider, celui-ci renvoie un 400. Le clamp evite ce 400 ; l'auto-continuation
    (call_llm_api_full / stream_llm_api) gere les documents depassant un seul appel.
    """
    want = int(current_app.config.get('LLM_MAX_TOKENS', 16384))
    cap = _PROVIDER_OUTPUT_CAP.get(provider_id)
    return min(want, cap) if cap else want


# Provider-specific parameters added to every OpenAI-format request
_PROVIDER_PARAMS: Dict[str, dict] = {
    'zai': {'thinking': {'type': 'disabled'}},
    'alibaba': {'thinking': {'type': 'disabled'}},
}

# Providers dont les modeles emettent du raisonnement par defaut en format
# Anthropic (/messages) : on desactive le thinking pour garder tout le budget
# max_tokens a la reponse finale (meme politique que _PROVIDER_PARAMS en OpenAI).
_ANTHROPIC_DISABLE_THINKING = {'opencode'}

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
    messages: Optional[list] = None,
) -> Tuple[str, dict, dict, str]:
    """Build (url, headers, payload, api_format) for a generation call.

    `messages` permet de fournir une conversation complete (reprise apres
    troncature : [user, assistant_partiel, user_hint]) ; a defaut on envoie un
    unique tour user contenant `prompt`.
    """
    api_format = _model_api_format(provider_id, model_id)
    msgs = messages if messages is not None else [{'role': 'user', 'content': prompt}]

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
            'max_tokens': _max_tokens(provider_id),
            'temperature': 0.7,
            'top_p': 0.95,
            'messages': msgs,
        }
        # Modeles a raisonnement routes en /messages : couper le thinking pour ne
        # pas consommer le budget max_tokens avant la reponse finale
        if provider_id in _ANTHROPIC_DISABLE_THINKING:
            payload['thinking'] = {'type': 'disabled'}
    else:
        url = provider['api_url']
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': model_id,
            'messages': msgs,
            'temperature': 0.7,
            'max_tokens': _max_tokens(provider_id),
            'top_p': 0.95,
        }
        payload.update(_PROVIDER_PARAMS.get(provider_id, {}))

    if stream:
        payload['stream'] = True
    return url, headers, payload, api_format


def _extract_content(data: dict, api_format: str) -> str:
    """Extract assistant text from a non-streaming API response.

    Le raisonnement (reasoning_content) n'est volontairement PAS utilise comme
    fallback : c'est du thinking, pas la reponse (meme politique que le stream).
    """
    if api_format == 'anthropic':
        blocks = data.get('content') or []
        return ''.join(
            b.get('text', '') for b in blocks
            if isinstance(b, dict) and b.get('type') == 'text'
        )
    if 'choices' in data and data['choices']:
        msg = data['choices'][0].get('message', {})
        return msg.get('content', '') or ''
    return ''


def _response_truncated(data: dict, api_format: str) -> bool:
    """True si une reponse synchrone a ete coupee au plafond max_tokens.

    Pendant : stop_reason=max_tokens (Anthropic), finish_reason=length (OpenAI).
    """
    if api_format == 'anthropic':
        return data.get('stop_reason') == 'max_tokens'
    choices = data.get('choices') or []
    if choices:
        return (choices[0] or {}).get('finish_reason') == 'length'
    return False


def _http_error_details(exc: http_requests.exceptions.HTTPError) -> Tuple[str, int]:
    """Map an upstream HTTP error to (message, suggested API status code)."""
    status = exc.response.status_code if exc.response is not None else 0
    if status == 401:
        return "Cle API invalide ou expiree. Verifiez dans la configuration.", 400
    if status == 429:
        return "Trop de requetes. Patientez quelques instants.", 429
    if status >= 500:
        return "Erreur serveur du provider. Reessayez plus tard.", 502

    # 4xx : remonter le message du provider (ex. modele inconnu, max_tokens trop haut),
    # sinon l'erreur est indebuggable cote utilisateur
    detail = ''
    try:
        body = exc.response.json() if exc.response is not None else {}
        err = body.get('error')
        raw = (err.get('message') if isinstance(err, dict) else None) or body.get('message') or ''
        detail = str(raw)[:200]
    except Exception:
        detail = ''
    message = f"Erreur HTTP {status} du provider"
    if detail:
        message += f" : {detail}"
        if 'max_tokens' in detail:
            message += " (essayez de reduire LLM_MAX_TOKENS)"
    return message, 502


def _read_timed_out(exc: Exception) -> bool:
    """True si une ConnectionError requests enveloppe un read timeout urllib3.

    Pendant la consommation d'un stream, requests re-leve ReadTimeoutError en
    ConnectionError (pas en Timeout) : sans cette detection, le timeout de
    lecture mid-stream afficherait une erreur technique brute.
    """
    return 'Read timed out' in str(exc)


def _call_once(
    provider: dict,
    provider_id: str,
    model_id: str,
    api_key: str,
    messages: list,
) -> Tuple[Optional[str], bool, Optional[str], int]:
    """Un appel synchrone. Retourne (contenu, tronque, erreur, status)."""
    url, headers, payload, api_format = _build_request(
        provider, provider_id, model_id, api_key, '', stream=False, messages=messages
    )
    try:
        logger.info('Calling %s model=%s format=%s', provider['name'], model_id, api_format)
        resp = http_requests.post(url, headers=headers, json=payload, timeout=_request_timeout())
        resp.raise_for_status()
        data = resp.json()

        content = _extract_content(data, api_format)
        truncated = _response_truncated(data, api_format)
        if content:
            return content, truncated, None, 200
        if api_format == 'openai' and 'choices' not in data:
            return None, False, "Format de reponse invalide", 502
        return None, truncated, ("Reponse vide du modele (le raisonnement a peut-etre consomme "
                                 "tout le budget LLM_MAX_TOKENS)"), 502

    except http_requests.exceptions.ConnectTimeout:
        return None, False, f"Connexion au provider impossible en {CONNECT_TIMEOUT}s. Reessayez.", 504
    except http_requests.exceptions.Timeout:
        return None, False, (f"Delai d'attente depasse ({_request_timeout()[1]}s sans reponse "
                             f"du provider). Reessayez."), 504
    except http_requests.exceptions.HTTPError as exc:
        message, status = _http_error_details(exc)
        return None, False, message, status
    except http_requests.exceptions.ConnectionError as exc:
        if _read_timed_out(exc):
            return None, False, (f"Delai d'attente depasse ({_request_timeout()[1]}s sans donnees "
                                 f"du provider). Reessayez."), 504
        return None, False, "Erreur de connexion. Verifiez votre acces internet.", 502
    except Exception as exc:
        logger.error('Unexpected LLM error: %s', exc, exc_info=True)
        return None, False, f"Erreur inattendue : {exc}", 500


def call_llm_api_full(
    prompt: str,
    provider_id: str,
    model_id: str,
    api_key: str,
) -> Tuple[Optional[str], bool, Optional[str], int]:
    """Appel synchrone avec auto-continuation. Retourne (resultat, tronque, erreur, status).

    Si un appel est coupe a max_tokens, on relance jusqu'a MAX_CONTINUATIONS fois
    en reinjectant le contenu deja produit comme tour assistant + une consigne de
    reprise, puis on concatene. `tronque` reste True seulement si le document est
    toujours incomplet apres epuisement des relances.
    """
    provider = get_provider_info(provider_id)
    if not provider:
        return None, False, f"Provider inconnu : {provider_id}", 400
    if not api_key:
        return None, False, f"Cle API manquante pour {provider['name']}", 400

    messages = [{'role': 'user', 'content': prompt}]
    full = ''
    truncated = False
    for turn in range(MAX_CONTINUATIONS + 1):
        content, turn_truncated, error, status = _call_once(
            provider, provider_id, model_id, api_key, messages
        )
        if error:
            # Du contenu deja accumule : renvoyer ce qu'on a (marque tronque) plutot
            # que de tout perdre sur une erreur survenant en pleine continuation
            if full:
                return full, True, None, 200
            return None, False, error, status
        full += content or ''
        if not turn_truncated:
            truncated = False
            break
        if not content or turn >= MAX_CONTINUATIONS:
            truncated = True
            break
        messages = [
            {'role': 'user', 'content': prompt},
            {'role': 'assistant', 'content': full},
            {'role': 'user', 'content': CONTINUE_HINT},
        ]

    logger.info('Success - %d chars (truncated=%s)', len(full), truncated)
    return full, truncated, None, 200


def call_llm_api(
    prompt: str,
    provider_id: str,
    model_id: str,
    api_key: str,
) -> Tuple[Optional[str], Optional[str], int]:
    """Call LLM API synchronously. Returns (result, error, status_code).

    Compat retro (3-uplet) : delegue a call_llm_api_full, qui auto-continue en cas
    de troncature. status_code is the suggested HTTP status for the API response
    (200 on success, 4xx for user-correctable errors, 5xx otherwise).
    """
    result, _truncated, error, status = call_llm_api_full(prompt, provider_id, model_id, api_key)
    return result, error, status


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


def _parse_stream_chunk(chunk: dict, api_format: str) -> Dict[str, Any]:
    """Parse a streaming event into {token, thinking, truncated, stop}.

    Le thinking (chaine de raisonnement des modeles type MiniMax M3, DeepSeek,
    GLM-5.1...) est separe de la reponse : il est affiche a part cote client et
    n'est jamais sauvegarde dans l'historique.
    """
    result: Dict[str, Any] = {'token': '', 'thinking': '', 'truncated': False, 'stop': False}

    if api_format == 'anthropic':
        ctype = chunk.get('type')
        if ctype == 'message_stop':
            result['stop'] = True
        elif ctype == 'message_delta':
            if (chunk.get('delta') or {}).get('stop_reason') == 'max_tokens':
                result['truncated'] = True
        elif ctype == 'content_block_delta':
            delta = chunk.get('delta') or {}
            if delta.get('type') == 'text_delta':
                result['token'] = delta.get('text', '') or ''
            elif delta.get('type') == 'thinking_delta':
                result['thinking'] = delta.get('thinking', '') or ''
        return result

    choices = chunk.get('choices') or []
    if not choices:
        return result
    choice = choices[0] or {}
    if choice.get('finish_reason') == 'length':
        result['truncated'] = True
    delta = choice.get('delta') or {}
    result['token'] = delta.get('content', '') or ''
    # reasoning_content (DeepSeek, GLM, Kimi) / reasoning (OpenRouter)
    result['thinking'] = delta.get('reasoning_content', '') or delta.get('reasoning', '') or ''
    return result


def _consume_turn(url: str, headers: dict, payload: dict, api_format: str):
    """Consomme UN appel stream. Yield les SSE thinking/token/error de ce tour.

    Retourne (texte, tronque, had_thinking, erreur) ; `erreur` non-None signale
    que l'event 'error' a deja ete emis et que la boucle appelante doit s'arreter.
    """
    turn_text = ''
    turn_truncated = False
    had_thinking = False
    try:
        resp = http_requests.post(
            url, headers=headers, json=payload,
            stream=True, timeout=_request_timeout(),
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            decoded = line.decode('utf-8')
            # 'data:' sans espace est valide en SSE (certains providers l'emettent)
            if not decoded.startswith('data:'):
                continue
            data_str = decoded[5:].strip()
            if data_str == '[DONE]':
                break
            try:
                chunk = json.loads(data_str)
                # Erreur upstream emise en cours de stream (apres le HTTP 200) :
                # la propager au client au lieu de terminer sur un faux 'done'
                upstream_error = _stream_error(chunk, api_format)
                if upstream_error:
                    logger.warning('Stream upstream error: %s', upstream_error)
                    yield _sse({'type': 'error', 'message': upstream_error})
                    return turn_text, turn_truncated, had_thinking, upstream_error
                parsed = _parse_stream_chunk(chunk, api_format)
                if parsed['truncated']:
                    turn_truncated = True
                if parsed['thinking']:
                    # Raisonnement du modele : affiche a part, jamais dans le resultat
                    had_thinking = True
                    yield _sse({'type': 'thinking', 'content': parsed['thinking']})
                if parsed['token']:
                    turn_text += parsed['token']
                    yield _sse({'type': 'token', 'content': parsed['token']})
                if parsed['stop']:
                    break
            except (json.JSONDecodeError, IndexError, KeyError):
                continue
        return turn_text, turn_truncated, had_thinking, None

    except http_requests.exceptions.ConnectTimeout:
        yield _sse({'type': 'error', 'message': (
            f"Connexion au provider impossible en {CONNECT_TIMEOUT}s. Reessayez."
        )})
        return turn_text, turn_truncated, had_thinking, 'error'
    except http_requests.exceptions.Timeout:
        yield _sse({'type': 'error', 'message': (
            f"Delai d'attente depasse ({_request_timeout()[1]}s sans donnees du provider)"
        )})
        return turn_text, turn_truncated, had_thinking, 'error'
    except http_requests.exceptions.HTTPError as exc:
        message, _ = _http_error_details(exc)
        yield _sse({'type': 'error', 'message': message})
        return turn_text, turn_truncated, had_thinking, 'error'
    except http_requests.exceptions.ChunkedEncodingError:
        yield _sse({'type': 'error', 'message': (
            "Flux interrompu par le provider (connexion coupee en cours de generation). Reessayez."
        )})
        return turn_text, turn_truncated, had_thinking, 'error'
    except http_requests.exceptions.ConnectionError as exc:
        # Pendant iter_lines, un read timeout urllib3 est re-leve en ConnectionError
        if _read_timed_out(exc):
            yield _sse({'type': 'error', 'message': (
                f"Delai d'attente depasse ({_request_timeout()[1]}s sans donnees du provider)"
            )})
        else:
            yield _sse({'type': 'error', 'message': (
                "Connexion au provider perdue en cours de generation. Reessayez."
            )})
        return turn_text, turn_truncated, had_thinking, 'error'
    except Exception as exc:
        logger.error('Stream error: %s', exc, exc_info=True)
        # Jamais de str(exc) brut au client (details techniques dans les logs)
        yield _sse({'type': 'error', 'message': "Erreur inattendue pendant le streaming. Reessayez."})
        return turn_text, turn_truncated, had_thinking, 'error'


def stream_llm_api(
    prompt: str,
    provider_id: str,
    model_id: str,
    api_key: str,
    continue_from: str = '',
) -> Generator[str, None, None]:
    """Stream LLM response as Server-Sent Events, avec auto-continuation.

    Si un tour est coupe a max_tokens, on relance (jusqu'a MAX_CONTINUATIONS) en
    reinjectant le contenu deja produit comme tour assistant + une consigne de
    reprise. Le flux de tokens reste continu cote client (un event 'continuing'
    signale la relance). 'done' n'est emis qu'a la fin ; truncated=True seulement
    si le document est toujours incomplet apres epuisement des relances.
    """
    provider = get_provider_info(provider_id)
    if not provider:
        yield _sse({'type': 'error', 'message': f'Provider inconnu : {provider_id}'})
        return
    if not api_key:
        yield _sse({'type': 'error', 'message': f'Cle API manquante pour {provider["name"]}'})
        return

    yield _sse({'type': 'start', 'message': 'Generation en cours...'})

    # continue_from : reprise manuelle apres troncature (le client renvoie le
    # document deja recu). full_content ne contient que le NOUVEAU texte ; le
    # 'done' renvoie base + nouveau (document complet a afficher/sauvegarder).
    base = continue_from or ''
    if base:
        messages = [
            {'role': 'user', 'content': prompt},
            {'role': 'assistant', 'content': base},
            {'role': 'user', 'content': CONTINUE_HINT},
        ]
    else:
        messages = [{'role': 'user', 'content': prompt}]
    full_content = ''
    truncated = False
    had_thinking = False

    for turn in range(MAX_CONTINUATIONS + 1):
        url, headers, payload, api_format = _build_request(
            provider, provider_id, model_id, api_key, '', stream=True, messages=messages
        )
        turn_text, turn_truncated, turn_thinking, error = yield from _consume_turn(
            url, headers, payload, api_format
        )
        full_content += turn_text
        had_thinking = had_thinking or turn_thinking
        if error is not None:
            # _consume_turn a deja emis l'event 'error'
            return
        if not turn_truncated:
            truncated = False
            break
        # Coupe a max_tokens : tour vide (rien a continuer) ou relances epuisees -> on s'arrete
        if not turn_text or turn >= MAX_CONTINUATIONS:
            truncated = True
            break
        messages = [
            {'role': 'user', 'content': prompt},
            {'role': 'assistant', 'content': base + full_content},
            {'role': 'user', 'content': CONTINUE_HINT},
        ]
        yield _sse({'type': 'continuing',
                    'message': 'Document long : poursuite automatique de la generation...'})

    # Stream termine sans aucune reponse : erreur explicite plutot qu'un
    # faux 'done' vide (toast de succes au-dessus d'un resultat vide)
    complete = base + full_content
    if not full_content:
        if base:
            # Continuation sans nouveau texte : rien a ajouter, renvoyer l'existant
            yield _sse({'type': 'done', 'content': complete, 'truncated': truncated})
            return
        if truncated:
            message = ("Budget de tokens entierement consomme par le raisonnement "
                       "du modele : augmentez LLM_MAX_TOKENS")
        elif had_thinking:
            message = "Le modele n'a produit que du raisonnement, sans reponse finale. Reessayez."
        else:
            message = "Reponse vide du modele"
        yield _sse({'type': 'error', 'message': message})
        return

    if truncated:
        logger.warning('Stream still truncated after %d continuations (%s/%s)',
                       MAX_CONTINUATIONS, provider_id, model_id)
    yield _sse({'type': 'done', 'content': complete, 'truncated': truncated})


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
