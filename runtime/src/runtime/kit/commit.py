"""What waits for a commit: an effect run once a session's transaction is committed, and dropped when it rolls back."""

from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from runtime.kit.loops import survive

# On a session's `info`: the effects its transaction owes once it is committed.
OWED = "kit.owed_after_commit"

type Effect = Callable[[], None]


# What leaves the database's reach (an email that carries a link to a row, a key forgotten on every
# gateway) is done after the commit, never inside the transaction: done before, a commit that fails
# leaves a link to a row that does not exist, and a request that reads between the two finds the old
# row and trusts it again. The effect is a plain call; one that must wait starts its own task.
def run_after_commit(session: AsyncSession, effect: Effect) -> None:
    """Run the effect once the session's transaction commits; a transaction rolled back runs nothing."""
    owed: list[Effect] | None = session.info.get(OWED)
    if owed is None:
        owed = session.info[OWED] = []
        event.listen(session.sync_session, "after_commit", _run_owed)
        event.listen(session.sync_session, "after_rollback", _drop_owed)
    owed.append(effect)


# The transaction is committed when this runs: an effect that raises is said and the rest still run,
# and the request that committed is answered as the success it was.
def _run_owed(session: Session) -> None:
    owed: list[Effect] = session.info.get(OWED, [])
    effects, owed[:] = list(owed), []
    for effect in effects:
        with survive("what a commit owed"):
            effect()


def _drop_owed(session: Session) -> None:
    owed: list[Effect] = session.info.get(OWED, [])
    owed.clear()
