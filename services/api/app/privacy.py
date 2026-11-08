"""Encryption and keyed fingerprints for consumer contact details."""
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken


def intake_enabled() -> bool:
    return os.getenv("ARLETION_CONSUMER_INTAKE_ENABLED", "false").strip().lower() == "true"


def consumer_storage_ready() -> bool:
    return (
        intake_enabled()
        and os.getenv("ARLETION_CONSUMER_STORAGE_APPROVED", "false").strip().lower() == "true"
        and bool(os.getenv("ARLETION_PII_ENCRYPTION_KEY"))
        and len(os.getenv("ARLETION_CONTACT_HASH_KEY", "")) >= 32
        and bool(os.getenv("ARLETION_CONSUMER_ACCESS_KEY"))
    )


def _fernet() -> Fernet:
    key = os.getenv("ARLETION_PII_ENCRYPTION_KEY", "")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise RuntimeError("ARLETION_PII_ENCRYPTION_KEY must be a valid Fernet key.") from None


def encrypt_contact(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_contact(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeEncodeError):
        raise RuntimeError("Consumer contact data cannot be decrypted with the configured key.") from None


def contact_fingerprint(phone: str | None, email: str | None) -> str:
    key = os.getenv("ARLETION_CONTACT_HASH_KEY", "")
    if len(key) < 32:
        raise RuntimeError("ARLETION_CONTACT_HASH_KEY must contain at least 32 characters.")
    normalized = "|".join([
        (phone or "").strip().replace(" ", "").lower(),
        (email or "").strip().lower(),
    ])
    return hmac.new(key.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def valid_consumer_access(supplied: str | None) -> bool:
    expected = os.getenv("ARLETION_CONSUMER_ACCESS_KEY", "")
    return bool(expected and supplied and hmac.compare_digest(supplied, expected))
