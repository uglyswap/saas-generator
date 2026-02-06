"""Template CRUD service."""
import logging
from typing import Optional, List, Tuple

from app import db
from app.models import Template
from app.utils.validators import (
    validate_template_name,
    validate_template_content,
    validate_description,
    extract_variables,
)

logger = logging.getLogger(__name__)


def get_user_templates(user_id: int) -> List[Template]:
    """Get all templates for a user, newest first."""
    return (
        Template.query
        .filter_by(user_id=user_id)
        .order_by(Template.updated_at.desc())
        .all()
    )


def get_template(template_id: int, user_id: int) -> Optional[Template]:
    """Get a single template owned by user."""
    return Template.query.filter_by(id=template_id, user_id=user_id).first()


def create_template(
    user_id: int,
    name: str,
    content: str,
    description: str = '',
    default_provider: str = 'zai',
    default_model: str = 'glm-4.7',
) -> Tuple[Optional[Template], Optional[str]]:
    """Create a new template. Returns (template, error)."""
    ok, err = validate_template_name(name)
    if not ok:
        return None, err
    ok, err = validate_template_content(content)
    if not ok:
        return None, err
    ok, err = validate_description(description)
    if not ok:
        return None, err

    variables = extract_variables(content)

    tpl = Template(
        user_id=user_id,
        name=name.strip(),
        description=(description or '').strip(),
        content=content.strip(),
        variables=variables,
        default_provider=default_provider,
        default_model=default_model,
    )
    db.session.add(tpl)
    db.session.commit()
    logger.info('Template created: id=%d user=%d', tpl.id, user_id)
    return tpl, None


def update_template(
    template_id: int,
    user_id: int,
    **kwargs,
) -> Tuple[Optional[Template], Optional[str]]:
    """Update an existing template. Returns (template, error)."""
    tpl = get_template(template_id, user_id)
    if not tpl:
        return None, "Template non trouve"

    if 'name' in kwargs:
        ok, err = validate_template_name(kwargs['name'])
        if not ok:
            return None, err
        tpl.name = kwargs['name'].strip()

    if 'content' in kwargs:
        ok, err = validate_template_content(kwargs['content'])
        if not ok:
            return None, err
        tpl.content = kwargs['content'].strip()
        tpl.variables = extract_variables(tpl.content)

    if 'description' in kwargs:
        ok, err = validate_description(kwargs['description'])
        if not ok:
            return None, err
        tpl.description = (kwargs['description'] or '').strip()

    if 'default_provider' in kwargs:
        tpl.default_provider = kwargs['default_provider']
    if 'default_model' in kwargs:
        tpl.default_model = kwargs['default_model']

    db.session.commit()
    logger.info('Template updated: id=%d user=%d', tpl.id, user_id)
    return tpl, None


def delete_template(template_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
    """Delete a template. Returns (success, error)."""
    tpl = get_template(template_id, user_id)
    if not tpl:
        return False, "Template non trouve"
    db.session.delete(tpl)
    db.session.commit()
    logger.info('Template deleted: id=%d user=%d', template_id, user_id)
    return True, None
