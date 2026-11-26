"""CR-FLOW-001: date eligibility is independent of dispatch snapshot membership."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from levelup.infra.public_http import CollectionError

KST = ZoneInfo("Asia/Seoul")
NotificationState = Literal["baseline", "pending", "suppressed", "notified"]


@dataclass(frozen=True)
class Eligibility:
    state: NotificationState
    eligible_on: date | None


def compute_eligibility(
    *,
    baseline: bool,
    epoch_kind: Literal["first_add", "resume", "readd"],
    epoch_started_at: datetime,
    first_seen_at: datetime,
    published_at: datetime | None,
    existing: Eligibility | None = None,
    reserved: bool = False,
) -> Eligibility:
    for value in (epoch_started_at, first_seen_at, published_at):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Timezone-aware timestamps required")
    # Sending/unknown/accepted reservations and settled states cannot gain another notification.
    if existing is not None and (existing.state != "pending" or reserved):
        return existing
    if reserved:
        raise ValueError("A reservation requires existing eligibility")
    if baseline:
        return Eligibility("baseline", None)
    if epoch_kind in ("resume", "readd") and published_at is not None:
        if published_at < epoch_started_at:
            return Eligibility("suppressed", None)
    first_day = first_seen_at.astimezone(KST).date()
    eligible_on = (
        max(published_at.astimezone(KST).date() + timedelta(days=1), first_day)
        if published_at is not None
        else first_day + timedelta(days=1)
    )
    return Eligibility("pending", eligible_on)


def match_article(
    keys: tuple[tuple[str, str], ...], aliases: dict[tuple[str, str], str]
) -> str | None:
    """Aliases must be scoped to one source by the persistence caller."""
    matches = {aliases[key] for key in keys if key in aliases}
    if len(matches) > 1:
        raise CollectionError("IDENTITY_CONFLICT")
    return next(iter(matches), None)
