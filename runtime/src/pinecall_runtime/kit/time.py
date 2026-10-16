"""Clocks and calendars: now in UTC, a day in a zone, the month a timestamp falls in."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pinecall_runtime.exceptions import ValidationError


def now() -> datetime:
    """Now, timezone-aware."""
    return datetime.now(UTC)


def epoch() -> float:
    """Now as seconds since the epoch, the stamp every log entry carries."""
    return datetime.now(UTC).timestamp()


def parse_zone(zone: str) -> ZoneInfo:
    """The IANA zone by name."""
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError(f"{zone!r} is not an IANA time zone (Europe/Madrid, America/Montevideo, UTC)") from None


def today_in(zone: str) -> date:
    """Today where the caller is, not where the box is."""
    return datetime.now(UTC).astimezone(parse_zone(zone)).date()


def month_of(ts: float) -> date:
    """The first day of the UTC month a timestamp falls in: usage is counted per month."""
    moment = datetime.fromtimestamp(ts, UTC)
    return date(moment.year, moment.month, 1)


def day_of(ts: float) -> date:
    """The UTC day a timestamp falls in."""
    return datetime.fromtimestamp(ts, UTC).date()
