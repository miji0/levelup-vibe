import base64

import pytest
from cryptography.exceptions import InvalidTag

from levelup.backup import postgres_env, seal, unseal

KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()


def test_encrypted_authenticated_backup():
    data = b"fixture database dump with tokens"
    result = seal(data, KEY)
    assert data not in result and result != seal(data, KEY)
    assert unseal(result, KEY) == data
    with pytest.raises(InvalidTag):
        unseal(result[:-1] + bytes([result[-1] ^ 1]), KEY)
    with pytest.raises(InvalidTag):
        unseal(result, base64.urlsafe_b64encode(b"x" * 32).decode())


def test_postgres_url_credentials_not_in_cli_and_ssl_preserved():
    env = postgres_env("postgresql+psycopg://owner:p%40ss@db.example.com:5433/data?sslmode=require")
    assert env["PGPASSWORD"] == "p@ss" and env["PGPORT"] == "5433" and env["PGSSLMODE"] == "require"


def test_database_backup_restore_preserves_duplicate_guard(settings, tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path
    from uuid import uuid4

    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from levelup.infra.db import ensure_owner
    from levelup.migrate import migrate

    url = os.environ.get("TEST_DATABASE_URL")
    if not url or not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        pytest.skip("Isolated PostgreSQL and matching pg_dump/pg_restore required")
    admin = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    names = ["backup_" + uuid4().hex, "restore_" + uuid4().hex]
    engines = []
    try:
        with admin.connect() as conn:
            for name in names:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
        from sqlalchemy.engine import make_url

        urls = [make_url(url).set(database=n).render_as_string(hide_password=False) for n in names]
        for target in urls:
            engines.append(create_engine(target, poolclass=NullPool))
        migrate(engines[0], Path(__file__).resolve().parents[2] / "db" / "migrations")
        ensure_owner(engines[0], settings)
        with engines[0].begin() as conn:
            owner = conn.execute(text("SELECT id FROM owner_settings")).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO job_runs(id,owner_id,kind,dedup_key,available_at,state) "
                    "VALUES (:id,:owner,'digest','digest/fixture/2026-11-27',"
                    "clock_timestamp(),'succeeded')"
                ),
                {"id": uuid4(), "owner": owner},
            )
        env = {
            **os.environ,
            "BACKUP_DATABASE_URL": urls[0],
            "RESTORE_DATABASE_URL": urls[1],
            "BACKUP_ENCRYPTION_KEY": KEY,
        }
        file = str(tmp_path / "db.lup")
        for command in [("create", file), ("verify", file), ("restore", file, "--isolated-target")]:
            subprocess.run(
                [sys.executable, "-m", "levelup.backup", *command],
                env=env,
                check=True,
                capture_output=True,
            )
        with engines[1].connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM schema_migrations")).scalar_one() == 3
            assert (
                conn.execute(
                    text("SELECT state FROM job_runs WHERE dedup_key='digest/fixture/2026-11-27'")
                ).scalar_one()
                == "succeeded"
            )
            assert conn.execute(text("SELECT count(*) FROM deliveries")).scalar_one() == 0
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            for name in names:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
