import base64
import os
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_origin: str = "http://localhost:3000"
    database_url: str = ""
    owner_google_sub: str = ""
    owner_email: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    token_encryption_key: str = ""
    token_encryption_key_id: str = "v1"
    mail_delivery_enabled: bool = False
    cron_secret: str = ""

    @model_validator(mode="after")
    def validate_origin(self):
        origin = urlsplit(self.app_origin)
        if origin.path or origin.query or origin.fragment or origin.username or origin.password:
            raise ValueError("APP_ORIGIN must contain only scheme and host/port")
        if not origin.hostname or origin.scheme not in {"http", "https"}:
            raise ValueError("Invalid APP_ORIGIN")
        if origin.scheme == "http" and origin.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Non-local origins require HTTPS")
        if os.environ.get("VERCEL") and origin.scheme != "https":
            raise ValueError("Vercel requires an explicit HTTPS APP_ORIGIN")
        if self.database_url and not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use PostgreSQL with psycopg")
        if self.token_encryption_key:
            if len(base64.urlsafe_b64decode(self.token_encryption_key)) != 32:
                raise ValueError("TOKEN_ENCRYPTION_KEY must encode 32 bytes")
        return self

    @property
    def secure_cookie(self) -> bool:
        return self.app_origin.startswith("https://")

    @property
    def ready(self) -> bool:
        return all(
            (
                self.database_url,
                self.owner_google_sub,
                self.owner_email,
                self.google_client_id,
                self.google_client_secret,
                self.token_encryption_key,
            )
        )
