"""What a verb reads of a person at a terminal: a secret on stdin, and a day typed as YYYY-MM-DD."""

import sys
from datetime import UTC, datetime

from runtime.exceptions import ValidationError

NOTHING_ON_STDIN = "the key is read from stdin, one line, and nothing came"
NOT_A_DAY = "{day}: a day, like 2026-09-01"


def read_secret_line() -> str:
    """One line of stdin, a secret; refused when nothing came."""
    line = sys.stdin.readline().strip()
    if not line:
        raise ValidationError(NOTHING_ON_STDIN)
    return line


def day_of(day: str | None) -> float | None:
    """The start of a day given as YYYY-MM-DD, in UTC; None when none was given."""
    if day is None:
        return None
    try:
        return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
    except ValueError:
        raise ValidationError(NOT_A_DAY.format(day=day)) from None
