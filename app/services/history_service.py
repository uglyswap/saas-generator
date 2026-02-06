"""History CRUD service with pagination."""
import logging
from typing import Optional, Tuple, Dict, Any

from flask import current_app

from app import db
from app.models import HistoryEntry

logger = logging.getLogger(__name__)


def get_user_history(
    user_id: int,
    page: int = 1,
    per_page: Optional[int] = None,
    template_id: Optional[int] = None,
    provider: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Get paginated history for a user with optional filters.

    Returns dict with 'entries', 'total', 'page', 'pages', 'per_page'.
    """
    if per_page is None:
        per_page = current_app.config.get('HISTORY_PER_PAGE', 20)

    query = HistoryEntry.query.filter_by(user_id=user_id)

    if template_id is not None:
        query = query.filter_by(template_id=template_id)
    if provider:
        query = query.filter_by(provider=provider)
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                HistoryEntry.template_name.ilike(like),
                HistoryEntry.result.ilike(like),
            )
        )

    query = query.order_by(HistoryEntry.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'entries': [e.to_dict() for e in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
        'per_page': per_page,
    }


def get_history_entry(entry_id: int, user_id: int) -> Optional[HistoryEntry]:
    """Get a single history entry owned by user."""
    return HistoryEntry.query.filter_by(id=entry_id, user_id=user_id).first()


def create_history_entry(
    user_id: int,
    template_id: Optional[int],
    template_name: str,
    variables: dict,
    provider: str,
    model: str,
    result: str,
) -> HistoryEntry:
    """Create a new history entry."""
    entry = HistoryEntry(
        user_id=user_id,
        template_id=template_id,
        template_name=template_name,
        variables=variables,
        provider=provider,
        model=model,
        result=result,
    )
    db.session.add(entry)

    # Enforce max entries per user
    max_entries = current_app.config.get('HISTORY_MAX_ENTRIES', 500)
    total = HistoryEntry.query.filter_by(user_id=user_id).count()
    if total > max_entries:
        overflow = (
            HistoryEntry.query
            .filter_by(user_id=user_id)
            .order_by(HistoryEntry.created_at.asc())
            .limit(total - max_entries)
            .all()
        )
        for old in overflow:
            db.session.delete(old)

    db.session.commit()
    logger.info('History entry created: id=%d user=%d', entry.id, user_id)
    return entry


def delete_history_entry(entry_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
    """Delete a history entry. Returns (success, error)."""
    entry = get_history_entry(entry_id, user_id)
    if not entry:
        return False, "Entree non trouvee"
    db.session.delete(entry)
    db.session.commit()
    logger.info('History entry deleted: id=%d user=%d', entry_id, user_id)
    return True, None


def clear_user_history(user_id: int) -> int:
    """Delete all history for a user. Returns count deleted."""
    count = HistoryEntry.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    logger.info('History cleared: %d entries for user=%d', count, user_id)
    return count
