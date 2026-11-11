"""The org a request acts for: named once for its statements, and set aside where the box acts."""

import asyncio
import contextvars
from collections.abc import Coroutine, Generator
from contextlib import contextmanager
from contextvars import ContextVar

# Row-level security: a transaction that names an org sees and writes that org's rows alone; one that
# names none is the box's, as the operator's endpoints and the loops are. The gateway names the org of
# the actor's key for the whole request.
SCOPED_ORG: ContextVar[str | None] = ContextVar("scoped_org", default=None)


def scope_to(org: str) -> None:
    """Name the org every transaction begun from here on in this request acts for."""
    SCOPED_ORG.set(org)


@contextmanager
def box_wide() -> Generator[None]:
    """Act as the box within the block: a service reading across orgs on purpose."""
    token = SCOPED_ORG.set(None)
    try:
        yield
    finally:
        SCOPED_ORG.reset(token)


def box_task[T](work: Coroutine[object, object, T]) -> asyncio.Task[T]:
    """Start the work as a task of the box's, whatever org the request starting it acts for."""
    context = contextvars.copy_context()
    context.run(SCOPED_ORG.set, None)
    return asyncio.create_task(work, context=context)
