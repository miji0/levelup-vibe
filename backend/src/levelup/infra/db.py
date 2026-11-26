from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from levelup.core.config import Settings


def engine_for(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )


def ensure_owner(engine: Engine, settings: Settings) -> None:
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT auth_subject FROM owner_settings")
        ).scalar_one_or_none()
        if existing is not None and existing != settings.owner_google_sub:
            raise ValueError("Configured owner differs from installed owner; refusing replacement")
        conn.execute(
            text("""
            INSERT INTO owner_settings (id, auth_subject, auth_email, created_at, updated_at)
            VALUES (:id, :subject, :email, :now, :now)
            ON CONFLICT (singleton) DO NOTHING
        """),
            {
                "id": uuid4(),
                "subject": settings.owner_google_sub,
                "email": settings.owner_email,
                "now": datetime.now(UTC),
            },
        )
