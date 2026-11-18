
import os

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured


def get_fernet():
    key = os.getenv("MIKROTIK_ENCRYPTION_KEY")

    if not key:
        raise ImproperlyConfigured(
            "MIKROTIK_ENCRYPTION_KEY is missing from the environment."
        )

    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise ImproperlyConfigured(
            "MIKROTIK_ENCRYPTION_KEY is invalid."
        )


def encrypt_password(password):
    if not password:
        raise ValueError("A MikroTik password is required.")

    return get_fernet().encrypt(password.encode()).decode()


def decrypt_password(encrypted_password):
    if not encrypted_password:
        raise ValueError("No encrypted MikroTik password is stored.")

    try:
        return get_fernet().decrypt(
            encrypted_password.encode()
        ).decode()
    except InvalidToken:
        raise ValueError(
            "Unable to decrypt the MikroTik password. "
            "Check your encryption key."
        )
