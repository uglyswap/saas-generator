"""Input validation functions."""
import re
from typing import Optional, Tuple, List

MAX_TEMPLATE_NAME_LENGTH = 200
MAX_TEMPLATE_CONTENT_LENGTH = 50_000
MAX_DESCRIPTION_LENGTH = 1_000
MAX_VARIABLE_VALUE_LENGTH = 10_000
MAX_API_KEY_LENGTH = 500
MIN_PASSWORD_LENGTH = 8
MAX_USERNAME_LENGTH = 80
MAX_EMAIL_LENGTH = 120


def validate_template_name(name: str) -> Tuple[bool, Optional[str]]:
    """Validate template name."""
    if not name or not name.strip():
        return False, "Le nom du template est obligatoire"
    name = name.strip()
    if len(name) > MAX_TEMPLATE_NAME_LENGTH:
        return False, f"Le nom ne peut pas depasser {MAX_TEMPLATE_NAME_LENGTH} caracteres"
    return True, None


def validate_template_content(content: str) -> Tuple[bool, Optional[str]]:
    """Validate template content."""
    if not content or not content.strip():
        return False, "Le contenu du template est obligatoire"
    if len(content.strip()) > MAX_TEMPLATE_CONTENT_LENGTH:
        return False, f"Le contenu ne peut pas depasser {MAX_TEMPLATE_CONTENT_LENGTH} caracteres"
    return True, None


def validate_description(desc: str) -> Tuple[bool, Optional[str]]:
    """Validate description field."""
    if desc and len(desc.strip()) > MAX_DESCRIPTION_LENGTH:
        return False, f"La description ne peut pas depasser {MAX_DESCRIPTION_LENGTH} caracteres"
    return True, None


def validate_variable_values(variables: dict, expected: List[str]) -> Tuple[bool, Optional[str]]:
    """Validate all variable values for a template."""
    if not isinstance(variables, dict):
        return False, "Format de variables invalide"
    for var_name in expected:
        value = variables.get(var_name, '')
        if not value or not str(value).strip():
            return False, f"La variable '{var_name}' est obligatoire"
        if len(str(value)) > MAX_VARIABLE_VALUE_LENGTH:
            return False, f"La variable '{var_name}' depasse {MAX_VARIABLE_VALUE_LENGTH} caracteres"
    return True, None


def validate_api_key(api_key: str) -> Tuple[bool, Optional[str]]:
    """Validate API key format."""
    if not api_key or not api_key.strip():
        return False, "La cle API est obligatoire"
    api_key = api_key.strip()
    if len(api_key) > MAX_API_KEY_LENGTH:
        return False, "La cle API est trop longue"
    return True, None


def validate_provider_id(provider_id: str, providers: dict) -> Tuple[bool, Optional[str]]:
    """Validate provider ID against known providers."""
    if not provider_id:
        return False, "Le provider est obligatoire"
    if provider_id not in providers:
        return False, f"Provider invalide: {provider_id}"
    return True, None


def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """Validate username."""
    if not username or not username.strip():
        return False, "Le nom d'utilisateur est obligatoire"
    username = username.strip()
    if len(username) < 3:
        return False, "Le nom d'utilisateur doit contenir au moins 3 caracteres"
    if len(username) > MAX_USERNAME_LENGTH:
        return False, f"Le nom d'utilisateur ne peut pas depasser {MAX_USERNAME_LENGTH} caracteres"
    if not re.match(r'^[\w\-_.]+$', username, re.UNICODE):
        return False, "Le nom d'utilisateur ne peut contenir que lettres, chiffres, tirets et underscores"
    return True, None


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """Validate email address."""
    if not email or not email.strip():
        return False, "L'email est obligatoire"
    email = email.strip()
    if len(email) > MAX_EMAIL_LENGTH:
        return False, f"L'email ne peut pas depasser {MAX_EMAIL_LENGTH} caracteres"
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return False, "Format d'email invalide"
    return True, None


def validate_password(password: str) -> Tuple[bool, Optional[str]]:
    """Validate password strength."""
    if not password:
        return False, "Le mot de passe est obligatoire"
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caracteres"
    if not re.search(r'[A-Z]', password):
        return False, "Le mot de passe doit contenir au moins une majuscule"
    if not re.search(r'[a-z]', password):
        return False, "Le mot de passe doit contenir au moins une minuscule"
    if not re.search(r'[0-9]', password):
        return False, "Le mot de passe doit contenir au moins un chiffre"
    return True, None


def extract_variables(content: str) -> List[str]:
    """Extract {variable} placeholders from template content.

    Matches any non-empty text inside single braces, including spaces.
    Examples: {name}, {nom du projet}, {cheval de course}
    """
    pattern = r'\{([^{}]+)\}'
    matches = re.findall(pattern, content, re.UNICODE)
    # Strip whitespace from edges and deduplicate while preserving order
    cleaned = [m.strip() for m in matches if m.strip()]
    return list(dict.fromkeys(cleaned))


def safe_substitute(template_content: str, variables: dict) -> str:
    """Safely substitute variables in template content.

    Uses regex single-pass replacement instead of str.format()
    to prevent template injection attacks. All placeholders are
    replaced simultaneously, so a value containing {other_var}
    is treated as literal text.
    """
    def _replacer(match: re.Match) -> str:
        key = match.group(1).strip()
        if key in variables:
            return str(variables[key])
        return match.group(0)  # Leave unknown placeholders as-is

    return re.sub(r'\{([^{}]+)\}', _replacer, template_content)
