"""Symmetric encryption helpers for sensitive fields.

We use Fernet (AES-128 CBC + HMAC) from the ``cryptography`` package. The
key is read from ``FIELD_ENCRYPTION_KEY``; if that is empty, a key is
derived from ``SECRET_KEY`` (acceptable for local development only).
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class FieldEncryptionError(RuntimeError):
    """Raised when a value cannot be decrypted."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    raw_key = (settings.FIELD_ENCRYPTION_KEY or "").strip()
    if raw_key:
        try:
            # If the user provided a valid Fernet key, use it directly.
            return Fernet(raw_key.encode("ascii"))
        except (ValueError, TypeError):
            # Otherwise treat it as an arbitrary passphrase.
            material = raw_key.encode("utf-8")
    else:
        material = settings.SECRET_KEY.encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    """Encrypt ``plaintext`` and return a URL-safe ASCII token."""
    if not plaintext:
        return ""
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`."""
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise FieldEncryptionError(
            "Could not decrypt the stored value. The encryption key may have "
            "changed since the value was written."
        ) from exc
