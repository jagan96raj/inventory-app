"""Strong password policy (Spec v15.6)."""

import re

_MIN_LENGTH = 8
_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"\d")
_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def validate_password_strength(password: str) -> None:
    """Raise ValueError when password does not meet policy."""
    failures: list[str] = []
    if len(password) < _MIN_LENGTH:
        failures.append("at least 8 characters")
    if not _UPPER.search(password):
        failures.append("one uppercase letter (A–Z)")
    if not _LOWER.search(password):
        failures.append("one lowercase letter (a–z)")
    if not _DIGIT.search(password):
        failures.append("one digit (0–9)")
    if not _SPECIAL.search(password):
        failures.append("one special character (e.g. !@#$%^&*)")
    if failures:
        raise ValueError("Password must include: " + "; ".join(failures) + ".")


def validate_new_password_field(password: str) -> str:
    validate_password_strength(password)
    return password
