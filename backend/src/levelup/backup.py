"""Encrypted PostgreSQL backups. Plaintext remains in a private temporary directory."""

import argparse
import base64
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

MAGIC = b"LEVELUP-BACKUP-v1\0"


def seal(data: bytes, key: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + AESGCM(base64.urlsafe_b64decode(key)).encrypt(nonce, data, MAGIC)


def unseal(data: bytes, key: str) -> bytes:
    if not data.startswith(MAGIC):
        raise ValueError("Unknown backup format")
    offset = len(MAGIC)
    return AESGCM(base64.urlsafe_b64decode(key)).decrypt(
        data[offset : offset + 12], data[offset + 12 :], MAGIC
    )


def postgres_env(url: str) -> dict[str, str]:
    parsed = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("PostgreSQL URL required")
    from urllib.parse import parse_qs

    query = parse_qs(parsed.query)
    env = {
        **os.environ,
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": unquote(parsed.path[1:]),
        "PGUSER": unquote(parsed.username or ""),
        "PGPASSWORD": unquote(parsed.password or ""),
        "PGCONNECT_TIMEOUT": "15",
        "PGSSLMODE": query.get("sslmode", ["prefer"])[0],
    }
    return env


def run(command: list[str], env: dict[str, str]):
    try:
        subprocess.run(command, env=env, check=True, capture_output=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise RuntimeError(
            "PostgreSQL backup/restore command failed; credentials withheld"
        ) from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["create", "verify", "restore"])
    parser.add_argument("file", type=Path)
    parser.add_argument("--isolated-target", action="store_true")
    args = parser.parse_args()
    key = os.environ["BACKUP_ENCRYPTION_KEY"]
    with tempfile.TemporaryDirectory(prefix="levelup-backup-") as directory:
        dump = Path(directory) / "database.dump"
        if args.mode == "create":
            run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--file",
                    str(dump),
                ],
                postgres_env(os.environ["BACKUP_DATABASE_URL"]),
            )
            args.file.parent.mkdir(parents=True, exist_ok=True)
            with args.file.open("xb") as output:
                os.chmod(args.file, 0o600)
                output.write(seal(dump.read_bytes(), key))
        else:
            dump.write_bytes(unseal(args.file.read_bytes(), key))
            run(["pg_restore", "--list", str(dump)], os.environ.copy())
            if args.mode == "restore":
                if not args.isolated_target:
                    raise ValueError("Restore requires an explicitly isolated, empty target")
                target = os.environ["RESTORE_DATABASE_URL"]
                if target == os.environ.get("BACKUP_DATABASE_URL"):
                    raise ValueError("Refusing restore to backup source")
                run(
                    [
                        "pg_restore",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-privileges",
                        "--dbname",
                        postgres_env(target)["PGDATABASE"],
                        str(dump),
                    ],
                    postgres_env(target),
                )
                engine = None
                try:
                    engine = create_engine(
                        target.replace("postgresql://", "postgresql+psycopg://", 1)
                    )
                    with engine.begin() as conn:
                        conn.execute(
                            text("""UPDATE auth_sessions SET revoked_at=clock_timestamp()
                            WHERE revoked_at IS NULL""")
                        )
                except SQLAlchemyError:
                    raise RuntimeError(
                        "Restored session revocation failed; credentials withheld"
                    ) from None
                finally:
                    if engine is not None:
                        engine.dispose()
    print("Encrypted backup " + args.mode + " completed")


if __name__ == "__main__":
    main()
