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


@pytest.mark.parametrize("restore_driver", ["postgresql+psycopg", "postgresql"])
def test_database_backup_restore_preserves_duplicate_guard(settings, tmp_path, restore_driver):
    import asyncio
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path
    from uuid import uuid4

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from test_collection_store import Core, add, item, rss

    from levelup.api.app import SESSION, create_app
    from levelup.core.security import digest
    from levelup.infra.db import ensure_owner
    from levelup.migrate import migrate
    from levelup.modules.tech.persistence import CollectionStore
    from levelup.modules.tech.worker import CollectionWorker

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
        tokens = ["restore-revoked-session", "restore-active-session"]

        def session_status(engine, token):
            with TestClient(create_app(settings, engine), base_url=settings.app_origin) as client:
                client.cookies.set(SESSION, token)
                return client.get("/api/v1/session").status_code

        with engines[0].begin() as conn:
            owner = conn.execute(text("SELECT id FROM owner_settings")).scalar_one()
            conn.execute(
                text("""INSERT INTO auth_sessions
                (id,owner_id,token_hash,csrf_token,created_at,expires_at)
                VALUES (:id,:owner,:hash,'test-csrf',statement_timestamp(),
                statement_timestamp()+interval '604800 seconds')"""),
                [{"id": uuid4(), "owner": owner, "hash": digest(token)} for token in tokens],
            )
            conn.execute(
                text(
                    "INSERT INTO job_runs(id,owner_id,kind,dedup_key,available_at,state) "
                    "VALUES (:id,:owner,'digest','digest/fixture/2026-11-27',"
                    "clock_timestamp(),'succeeded')"
                ),
                {"id": uuid4(), "owner": owner},
            )
            connection = uuid4()
            conn.execute(
                text("""INSERT INTO gmail_connections
                (id,owner_id,google_subject,email,scopes,state,created_at,updated_at)
                VALUES (:id,:owner,'owner-123','owner@example.com','{gmail.send}',
                'connected',clock_timestamp(),clock_timestamp())"""),
                {"id": connection, "owner": owner},
            )
            conn.execute(
                text("""INSERT INTO deliveries
                (id,owner_id,kind,gmail_connection_id,connection_version,revision,
                request_key,mime_message_id,from_address,to_address,subject,mime_payload,
                payload_sha256,state,provider_message_id,prepared_at,submitted_at,accepted_at)
                VALUES (:id,:owner,'test',:connection,1,1,'restore-fixture',
                '<restore-fixture@example.com>','owner@example.com','owner@example.com',
                'Preserved delivery',:payload,'fixture-hash','accepted','fixture-provider-id',
                clock_timestamp(),clock_timestamp(),clock_timestamp())"""),
                {"id": uuid4(), "owner": owner, "connection": connection, "payload": b"fixture"},
            )
        store = CollectionStore(engines[0])
        add(store, owner)
        worker = CollectionWorker(store, Core(rss(item("preserved", "Preserved article"))))
        assert asyncio.run(worker.run_next(owner)) == "success"
        with engines[0].begin() as conn:
            conn.execute(
                text("""UPDATE article_states SET is_read=true,is_saved=true,
                read_at=clock_timestamp(),saved_at=clock_timestamp()""")
            )
        preserved_tables = ("articles", "article_states", "deliveries", "job_runs")
        with engines[0].connect() as conn:
            preserved = {
                table: conn.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings().all()
                if table != "article_states"
                else conn.execute(text("SELECT * FROM article_states ORDER BY article_id"))
                .mappings()
                .all()
                for table in preserved_tables
            }
        assert all(session_status(engines[0], token) == 200 for token in tokens)
        env = {
            **os.environ,
            "BACKUP_DATABASE_URL": urls[0],
            "RESTORE_DATABASE_URL": make_url(urls[1])
            .set(drivername=restore_driver)
            .render_as_string(hide_password=False),
            "BACKUP_ENCRYPTION_KEY": KEY,
        }
        file = str(tmp_path / "db.lup")
        for command in [("create", file), ("verify", file), ("restore", file, "--isolated-target")]:
            if command[0] == "restore":
                with engines[0].begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE auth_sessions SET revoked_at=clock_timestamp() "
                            "WHERE token_hash=:hash"
                        ),
                        {"hash": digest(tokens[0])},
                    )
                assert session_status(engines[0], tokens[0]) == 401
                assert session_status(engines[0], tokens[1]) == 200
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
            for table in preserved_tables:
                column = "article_id" if table == "article_states" else "id"
                assert (
                    conn.execute(text(f"SELECT * FROM {table} ORDER BY {column}")).mappings().all()
                    == preserved[table]
                )
            assert conn.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one() == 2
            assert (
                conn.execute(
                    text("SELECT count(*) FROM auth_sessions WHERE revoked_at IS NULL")
                ).scalar_one()
                == 0
            )
        assert all(session_status(engines[1], token) == 401 for token in tokens)
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            for name in names:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_restore_session_revocation_failure_is_not_reported_as_success(
    monkeypatch, tmp_path, capsys
):
    from sqlalchemy.exc import SQLAlchemyError

    from levelup import backup

    file = tmp_path / "db.lup"
    file.write_bytes(seal(b"dump fixture", KEY))
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", KEY)
    monkeypatch.setenv(
        "RESTORE_DATABASE_URL", "postgresql://owner:password@db.example.com/restored"
    )
    monkeypatch.setattr("sys.argv", ["backup", "restore", str(file), "--isolated-target"])
    monkeypatch.setattr(backup, "run", lambda *args: None)

    def unavailable_engine(url):
        raise SQLAlchemyError("sensitive connection details")

    monkeypatch.setattr(backup, "create_engine", unavailable_engine)
    with pytest.raises(RuntimeError, match="Restored session revocation failed") as error:
        backup.main()
    assert "sensitive" not in str(error.value)
    assert "completed" not in capsys.readouterr().out
