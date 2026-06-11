"""User configuration resolution service - general default provider/model."""
import logging
from typing import Optional, Tuple

from flask import current_app

from app import db
from app.models import ProviderConfig, User

logger = logging.getLogger(__name__)


def get_user_default(user_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Resolve the user's general default as (provider_id, model_id).

    Resolution order:
    1. User.default_provider + the selected model of its ProviderConfig
       (fallback: the provider's default_model from config)
    2. First provider having a selected model for this user
    3. (None, None) when nothing is configured
    """
    providers = current_app.config.get('PROVIDERS', {})
    user = db.session.get(User, user_id)

    # Une seule requete pour toutes les configs provider de l'utilisateur
    configs = {
        pc.provider_id: pc
        for pc in ProviderConfig.query.filter_by(user_id=user_id).all()
    }

    if user and user.default_provider and user.default_provider in providers:
        pc = configs.get(user.default_provider)
        model = (pc.selected_model if pc else '') or providers[user.default_provider].get('default_model', '')
        return user.default_provider, model

    for pid in providers:
        pc = configs.get(pid)
        if pc and pc.selected_model:
            return pid, pc.selected_model
    return None, None


def get_provider_model_for_user(user_id: int, provider_id: str) -> str:
    """Best model for a given provider: user's selected model, else provider default."""
    providers = current_app.config.get('PROVIDERS', {})
    pc = ProviderConfig.query.filter_by(user_id=user_id, provider_id=provider_id).first()
    return (pc.selected_model if pc else '') or providers.get(provider_id, {}).get('default_model', '')
