"""Tests for input validation functions."""
import pytest
from app.utils.validators import (
    validate_template_name,
    validate_template_content,
    validate_variable_values,
    validate_api_key,
    validate_username,
    validate_email,
    validate_password,
    extract_variables,
    safe_substitute,
)


class TestTemplateName:
    def test_valid_name(self):
        ok, err = validate_template_name('Mon Template')
        assert ok is True
        assert err is None

    def test_empty_name(self):
        ok, err = validate_template_name('')
        assert ok is False

    def test_whitespace_only(self):
        ok, err = validate_template_name('   ')
        assert ok is False

    def test_too_long(self):
        ok, err = validate_template_name('a' * 201)
        assert ok is False


class TestTemplateContent:
    def test_valid_content(self):
        ok, err = validate_template_content('Hello {name}')
        assert ok is True

    def test_empty_content(self):
        ok, err = validate_template_content('')
        assert ok is False

    def test_too_long(self):
        ok, err = validate_template_content('x' * 50_001)
        assert ok is False


class TestVariableValues:
    def test_valid_variables(self):
        ok, err = validate_variable_values({'name': 'John', 'city': 'Paris'}, ['name', 'city'])
        assert ok is True

    def test_missing_variable(self):
        ok, err = validate_variable_values({'name': 'John'}, ['name', 'city'])
        assert ok is False
        assert 'city' in err

    def test_empty_value(self):
        ok, err = validate_variable_values({'name': ''}, ['name'])
        assert ok is False

    def test_too_long_value(self):
        ok, err = validate_variable_values({'name': 'x' * 10_001}, ['name'])
        assert ok is False


class TestApiKey:
    def test_valid_key(self):
        ok, _ = validate_api_key('sk-abc123-def456')
        assert ok is True

    def test_empty_key(self):
        ok, _ = validate_api_key('')
        assert ok is False

    def test_too_long_key(self):
        ok, _ = validate_api_key('k' * 501)
        assert ok is False


class TestUsername:
    def test_valid_username(self):
        ok, _ = validate_username('john_doe')
        assert ok is True

    def test_too_short(self):
        ok, _ = validate_username('ab')
        assert ok is False

    def test_too_long(self):
        ok, _ = validate_username('a' * 81)
        assert ok is False

    def test_invalid_characters(self):
        ok, _ = validate_username('john doe!')
        assert ok is False


class TestEmail:
    def test_valid_email(self):
        ok, _ = validate_email('user@example.com')
        assert ok is True

    def test_invalid_email(self):
        ok, _ = validate_email('not-an-email')
        assert ok is False

    def test_empty_email(self):
        ok, _ = validate_email('')
        assert ok is False


class TestPassword:
    def test_strong_password(self):
        ok, _ = validate_password('MyPass123')
        assert ok is True

    def test_too_short(self):
        ok, _ = validate_password('Ab1')
        assert ok is False

    def test_no_uppercase(self):
        ok, _ = validate_password('password123')
        assert ok is False

    def test_no_lowercase(self):
        ok, _ = validate_password('PASSWORD123')
        assert ok is False

    def test_no_digit(self):
        ok, _ = validate_password('PasswordABC')
        assert ok is False


class TestExtractVariables:
    def test_basic_extraction(self):
        result = extract_variables('Hello {name}, welcome to {city}')
        assert result == ['name', 'city']

    def test_no_variables(self):
        result = extract_variables('Hello world')
        assert result == []

    def test_duplicate_removal(self):
        result = extract_variables('{name} and {name} and {other}')
        assert result == ['name', 'other']

    def test_nested_braces_ignored(self):
        result = extract_variables('{{not_a_var}} but {real_var}')
        assert 'real_var' in result

    def test_unicode_variables(self):
        result = extract_variables('{nom} et {prenom}')
        assert 'nom' in result
        assert 'prenom' in result


class TestSafeSubstitute:
    def test_basic_substitution(self):
        result = safe_substitute('Hello {name}!', {'name': 'World'})
        assert result == 'Hello World!'

    def test_multiple_variables(self):
        result = safe_substitute('{a} and {b}', {'a': 'X', 'b': 'Y'})
        assert result == 'X and Y'

    def test_missing_variable_left_as_is(self):
        result = safe_substitute('Hello {name}', {})
        assert result == 'Hello {name}'

    def test_injection_attempt_is_safe(self):
        malicious = '"; DROP TABLE users; --'
        result = safe_substitute('Value: {input}', {'input': malicious})
        assert malicious in result
        # The malicious content is treated as literal text, not executed
