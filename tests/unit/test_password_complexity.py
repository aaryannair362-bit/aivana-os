"""
Unit tests for app.auth.validate_password_complexity -- a pure function, so these are true
unit tests with no DB/network involved.

Source: backend/app/auth.py:22-53. Rules (in the order the function checks them):
  1. length 12-128
  2. at least one uppercase, one lowercase, one digit, one special char
  3. no 3-character ascending sequence (case-insensitive; e.g. "abc", "123")
  4. no 3 identical characters in a row (e.g. "aaa")
  5. no substring match against ['qwerty', 'asdfg', 'zxcvb', 'password', 'admin'] (case-insensitive)
  6. no substring match against the local part of the user's email (case-insensitive)
"""
import pytest
from app.auth import validate_password_complexity


def test_valid_password_at_minimum_length_boundary_12_chars():
    # exactly 12 chars, satisfies every rule
    pw = "Xk9!mQ7#pLz1"
    assert len(pw) == 12
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is True
    assert error == ""


def test_password_11_chars_rejected_just_below_minimum():
    pw = "Xk9!mQ7#pL1"  # 11 chars
    assert len(pw) == 11
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert "at least 12" in error


def test_valid_password_at_maximum_length_boundary_128_chars():
    # build a 128-char password with no sequential/repeated runs and no banned substrings
    core = "Xk9#mQ7!pLz1"
    pw = (core * 11)[:128]
    assert len(pw) == 128
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is True, error


def test_password_129_chars_rejected_just_above_maximum():
    core = "Xk9#mQ7!pLz1"
    pw = (core * 11)[:129]
    assert len(pw) == 129
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert "no more than 128" in error


@pytest.mark.parametrize(
    "pw,missing",
    [
        ("lowercase123!only", "uppercase"),
        ("UPPERCASE123!ONLY", "lowercase"),
        ("NoDigitsHere!!!!!", "number"),
        ("NoSpecialChars1234", "special character"),
    ],
)
def test_missing_character_class_rejected(pw, missing):
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert missing in error


@pytest.mark.parametrize("pw", ["Xkabc123!mQpz", "Xk9!123mQ#pLz", "MnZ0Xkabc9!Qz"])
def test_sequential_characters_rejected(pw):
    """Any 3-char ascending run (letters or digits, case-insensitive) is rejected."""
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert "sequential" in error


def test_sequential_check_is_case_insensitive():
    # "AbC" normalizes to "abc" which is a sequential run
    pw = "XkAbC9!mQpLz1"
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert "sequential" in error


@pytest.mark.parametrize("pw", ["Xkaaa9!mQpLz1", "Xk999!mQpLzA1"])
def test_repeated_characters_rejected(pw):
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert "repeated" in error


@pytest.mark.parametrize("pattern", ["qwerty", "asdfg", "zxcvb", "password", "admin"])
def test_common_pattern_substrings_rejected(pattern):
    # embed the banned pattern inside an otherwise-valid password
    pw = f"Xk9!{pattern}Qz1L#"
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert pattern in error


def test_common_pattern_check_is_case_insensitive():
    pw = "Xk9!QWERTYQz1L#"
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert "qwerty" in error


def test_email_local_part_reuse_rejected():
    valid, error = validate_password_complexity("Jsmith2024!Secure#", "jsmith@example.com")
    assert valid is False
    assert "email" in error


def test_email_local_part_reuse_rejected_case_insensitively():
    valid, error = validate_password_complexity("JSMITH2024!Secure#", "jsmith@example.com")
    assert valid is False
    assert "email" in error


def test_email_domain_part_is_not_checked_only_local_part():
    # the domain "example" appearing in the password should NOT trigger the email-reuse rule
    valid, error = validate_password_complexity("Example9!mQpLz1#", "jsmith@example.com")
    assert valid is True, error


def test_unicode_only_letters_do_not_satisfy_ascii_case_requirements():
    """
    Documents actual behavior: [A-Z]/[a-z] regex classes are ASCII-only, so a password whose
    only "letters" are accented Unicode characters (e.g. from a non-English name) will NOT be
    recognized as having upper/lowercase letters, even though it visually has mixed case. This
    is a real internationalization gap for a healthcare system likely to have non-English
    users -- flagged in TEST_NOTES.md rather than silently changed, since tightening/loosening
    Unicode handling is a product decision, not an obvious bug fix.
    """
    pw = "Österreich9!#"  # visually has "upper" Ö and lowercase, but Ö isn't in [A-Z]
    valid, error = validate_password_complexity(pw, "someone@example.com")
    assert valid is False
    assert "uppercase" in error


def test_empty_password_rejected_on_length_not_crash():
    valid, error = validate_password_complexity("", "someone@example.com")
    assert valid is False
    assert "at least 12" in error


def test_email_without_at_symbol_does_not_crash():
    # email.split('@')[0] on a string with no '@' just yields the whole string -- no crash
    valid, error = validate_password_complexity("Xk9!mQ7#pLz1", "not-an-email")
    assert valid is True, error


def test_length_checked_before_composition_rules():
    """A too-short password should fail on length, not report a composition issue instead."""
    valid, error = validate_password_complexity("short", "someone@example.com")
    assert valid is False
    assert "at least 12" in error
