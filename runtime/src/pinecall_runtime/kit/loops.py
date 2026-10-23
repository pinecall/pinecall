"""A loop that goes on: what one item or one pass raises is said, with where it was, and never ends the loop."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from pinecall_runtime.postgres import is_cancellation

logger = logging.getLogger(__name__)


@dataclass
class Survival:
    """How the block ended: `failed` once it raised and was said instead."""

    failed: bool = False


# Around the body of an item or of a pass, in sync or async code: what it raises is said and the
# loop goes on to the next, so one call, room or org it cannot read never stops what it does for
# every other. A cancellation goes through: it is the loop being stopped. The exception is logged
# with its traceback, and `on` names the call, the org or the room it was on. What the loop itself
# ends on (a socket that closed) is named in `unless`, and raised. A loop that must know which
# items failed reads `failed` off the block's `as`.
@contextmanager
def survived(what: str, on: str | None = None, *, unless: tuple[type[Exception], ...] = ()) -> Generator[Survival]:
    """Say what raised in the block, and where, instead of raising it; cancellation still raises."""
    outcome = Survival()
    try:
        yield outcome
    except Exception as failed:
        if is_cancellation(failed) or isinstance(failed, unless):
            raise
        outcome.failed = True
        logger.warning("%s failed%s", what, "" if on is None else f" on {on}", exc_info=True)
