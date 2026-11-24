"""What a domain above the live side is handed to reach an agent's app: who takes a call, one opened, one ended."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.calls.context import CallContext
from runtime.exceptions import NotFound
from runtime.live.holders import Registration
from runtime.live.parts import LiveParts
from runtime.live.service import seal
from runtime.live.service.ending import End, Sealing
from runtime.live.service.written import WrittenSetup, explain_nobody, open_written, open_written_as
from runtime.live.sockets import SocketId
from runtime.session import service as session
from runtime.wire.events import ErrorEvent

NEVER_SERVED = "never_served"
NOT_JUDGED_NEVER_SERVED = "no worker ever took the call: there was nothing to judge"


# What a domain above this one is handed to reach an agent's app (`evals`, which plays callers against
# it): one object of the live side's own, built once in the lifespan. `LiveParts` stays inside it.
class ServingApps:
    """The apps that serve agents here, as a domain above reaches them: which takes a call, a call opened on it."""

    def __init__(self, live: LiveParts) -> None:
        self._live = live

    def find(self, scope: Scope, slug: str, app: SocketId | None = None) -> Registration | None:
        """The socket a call opened in the scope goes to: the one named, else the newest that takes it; or None."""
        return self._live.holders.find_serving(scope, slug, app)

    def get(self, scope: Scope, slug: str, app: SocketId | None = None) -> Registration:
        """The socket a call opened in the scope goes to; refused, saying why, when no app takes it."""
        found = self.find(scope, slug, app)
        if found is None:
            raise NotFound(explain_nobody(self._live, scope, slug, app))
        return found

    # A call that was given an id and never a worker has nobody to end it. Its reason goes on its log
    # as an error nothing recovers from, which is how a call that never began says why, and it is ended
    # by the one end every call has. Until 2026-11-24 such a call was left with no entry and no end,
    # and whoever followed its log waited for good.
    async def end_never_served(self, call: str, agent: str, why: str) -> None:
        """End a call no worker ever took: why on its log, then its end, its summary and its score."""
        live = self._live
        said = ErrorEvent(code=NEVER_SERVED, message=why, recoverable=False)
        await live.logs.writing(call, agent).append("error", said.dump())
        end = End("error", ended_at=live.store.clock(), duration_s=0.0, not_judged=NOT_JUDGED_NEVER_SERVED)
        await seal.end_unserved(live, call, agent, Sealing(outcome=why, end=end))

    def still_holds(self, registration: Registration) -> bool:
        """Whether the socket still holds the agent it was found holding."""
        holders = self._live.holders
        return holders.find_on_socket(registration.owner, registration.scope.env, registration.slug) is not None

    async def open_written(
        self,
        session_: AsyncSession,
        registration: Registration,
        context: CallContext,
        *,
        test: Mapping[str, Any] | None = None,
    ) -> session.Session:
        """A new written call on the socket, as the scope's settings run the agent; admitted and unstarted."""
        return await open_written(session_, self._live, registration, context, test=test)

    async def open_written_as(
        self, session_: AsyncSession, registration: Registration, context: CallContext, setup: WrittenSetup
    ) -> session.Session:
        """A new written call on the socket, on the setup given; admitted and unstarted."""
        return await open_written_as(session_, self._live, registration, context, setup)
