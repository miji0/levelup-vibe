"""OP-01: owner-run receipt verification. This command never sends email."""

import argparse
from uuid import UUID

from sqlalchemy import text

from levelup.core.config import Settings
from levelup.infra.db import engine_for
from levelup.infra.gmail import SendOutcome
from levelup.infra.public_http import CollectionError
from levelup.modules.tech.mail import MailService
from levelup.modules.tech.persistence import OWNER_LOCK, locked_connection, prepare_transaction


def verify(service, owner, delivery, outcome, note, provider_id=None):
    if outcome not in ("confirmed_accepted", "confirmed_not_accepted", "unresolved"):
        raise CollectionError("INVALID_RECEIPT")
    if not note.strip() or len(note) > 1000 or any(ord(c) < 32 for c in note):
        raise CollectionError("INVALID_RECEIPT")
    if outcome == "confirmed_accepted" and not provider_id:
        raise CollectionError("INVALID_RECEIPT")
    with locked_connection(service.engine, OWNER_LOCK, owner) as conn, conn.begin():
        prepare_transaction(conn)
        saved = (
            conn.execute(
                text("SELECT * FROM deliveries WHERE id=:id AND owner_id=:owner FOR UPDATE"),
                {"id": delivery, "owner": owner},
            )
            .mappings()
            .one_or_none()
        )
        if (
            saved is None
            or saved["state"] != "unknown"
            or saved["verification_outcome"] in ("confirmed_accepted", "confirmed_not_accepted")
        ):
            raise CollectionError("INVALID_RECEIPT")
        state = "unknown"
        if outcome != "unresolved":
            state = service._record(
                conn,
                owner,
                delivery,
                saved["payload_sha256"],
                SendOutcome(
                    "accepted" if outcome == "confirmed_accepted" else "rejected",
                    provider_id=provider_id,
                ),
            )
        conn.execute(
            text("""UPDATE deliveries SET verification_outcome=:outcome,
            verification_note=:note,verified_at=clock_timestamp() WHERE id=:id"""),
            {"outcome": outcome, "note": note, "id": delivery},
        )
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", required=True, type=UUID)
    parser.add_argument(
        "--outcome",
        required=True,
        choices=["confirmed_accepted", "confirmed_not_accepted", "unresolved"],
    )
    parser.add_argument(
        "--note", required=True, help="Evidence location; do not include tokens or MIME bodies"
    )
    parser.add_argument("--provider-id")
    args = parser.parse_args()
    settings = Settings()
    engine = engine_for(settings)
    try:
        with engine.connect() as conn:
            owner = conn.execute(
                text("SELECT id FROM owner_settings WHERE auth_subject=:sub"),
                {"sub": settings.owner_google_sub},
            ).scalar_one()
        print(
            verify(
                MailService(engine, settings),
                owner,
                args.delivery,
                args.outcome,
                args.note,
                args.provider_id,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
