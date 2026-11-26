from datetime import UTC, datetime, timedelta

from conftest import FakeGoogle
from fastapi.testclient import TestClient
from test_collection_store import Core, add, execute, rows

from levelup.api.app import create_app
from levelup.modules.tech.scheduler import tick


def test_scheduler_no_secret_no_work(db, settings):
    at = datetime(2026, 11, 27, 0, tzinfo=UTC)
    settings.cron_secret = "fixture-secret-long-enough"
    with TestClient(create_app(settings, db, FakeGoogle(), clock=lambda: at)) as client:
        assert client.post("/api/internal/schedules/hourly").status_code == 401
        headers = {"Authorization": "Bearer " + settings.cron_secret}
        assert client.post("/api/internal/schedules/hourly", headers=headers).status_code == 400
        headers["ce-vssscheduledat"] = (at - timedelta(days=1)).isoformat()
        assert client.post("/api/internal/schedules/digest", headers=headers).status_code == 400
    assert not rows(db, "SELECT * FROM job_runs")


async def test_duplicate_schedule_bounded_collection_baseline(db, settings):
    owner = rows(db, "SELECT id FROM owner_settings")[0]["id"]
    from levelup.modules.tech.persistence import CollectionStore

    add(CollectionStore(db), owner)
    at = datetime(2026, 11, 27, 0, tzinfo=UTC)
    execute(db, "UPDATE owner_settings SET created_at='2020-01-01T00:00:00Z'")
    await tick(db, settings, Core(), None, at, at, "hourly", lambda: at)
    first = len(rows(db, "SELECT * FROM job_runs"))
    await tick(db, settings, Core(), None, at, at, "hourly", lambda: at)
    assert len(rows(db, "SELECT * FROM job_runs")) == first
    assert rows(db, "SELECT state FROM digests")[0]["state"] == "missed"
