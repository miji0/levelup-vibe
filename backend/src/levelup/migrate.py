"""Apply immutable SQL migrations. Use only against the explicitly configured database."""

import hashlib
from pathlib import Path

from sqlalchemy import text

from levelup.core.config import Settings
from levelup.infra.db import engine_for, ensure_owner


def migrate(engine, directory: Path) -> None:
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(41082301)"))
        conn.execute(
            text("""CREATE TABLE IF NOT EXISTS schema_migrations (
            name text PRIMARY KEY, checksum text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now())""")
        )
        for path in sorted(directory.glob("*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            prior = conn.execute(
                text("SELECT checksum FROM schema_migrations WHERE name=:name"), {"name": path.name}
            ).scalar_one_or_none()
            if prior is not None:
                if prior != checksum:
                    raise ValueError("Applied migration changed: " + path.name)
                continue
            conn.exec_driver_sql(sql)
            conn.execute(
                text("INSERT INTO schema_migrations(name, checksum) VALUES (:name, :sum)"),
                {"name": path.name, "sum": checksum},
            )


if __name__ == "__main__":
    settings = Settings()
    if not settings.database_url or not settings.owner_google_sub or not settings.owner_email:
        raise SystemExit("Set DATABASE_URL, OWNER_GOOGLE_SUB and OWNER_EMAIL before migrating")
    engine = engine_for(settings)
    migrate(engine, Path(__file__).resolve().parents[3] / "db" / "migrations")
    ensure_owner(engine, settings)
    engine.dispose()
