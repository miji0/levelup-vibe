import base64
import hashlib
import secrets
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def random_token() -> str:
    return secrets.token_urlsafe(32)


def safe_return_to(value: str) -> str:
    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or "\\" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or "%" in value
    ):
        return "/"
    return value


class Cipher:
    def __init__(self, key: str):
        self.aes = AESGCM(base64.urlsafe_b64decode(key))

    def encrypt(self, value: str, purpose: str) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + self.aes.encrypt(nonce, value.encode(), purpose.encode())

    def decrypt(self, value: bytes, purpose: str) -> str:
        return self.aes.decrypt(value[:12], value[12:], purpose.encode()).decode()
