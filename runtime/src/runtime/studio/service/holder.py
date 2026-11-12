"""Every Studio agent of the box, held by this gateway: a socket per org and env, kept as the releases say."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Env
from runtime.kit.crypto import Vault
from runtime.kit.loops import survive
from runtime.live import service as live
from runtime.studio.repository import StudioAgentRepository
from runtime.studio.service import definition as definitions
from runtime.studio.service import fetch
from runtime.studio.service.socket import StudioSocket
from runtime.wire.studio import Definition

logger = logging.getLogger(__name__)


# The word that an org's agents changed is a hint and the look at the database is the guarantee: a
# word lost on the signal, or a socket that refused an agent, is mended at the next look, which the
# gateway takes as it starts, each time it lost the signal, and every minute (`tasks`).
class Holder:
    """The Studio agents this gateway holds, a socket for each org and env that has any."""

    def __init__(
        self,
        sockets: live.AppSockets,
        sessions: async_sessionmaker[AsyncSession],
        vault: Vault,
        fetcher: fetch.Fetcher,
    ) -> None:
        """Holding nothing until the first look."""
        self.fetcher = fetcher
        self._sockets = sockets
        self._sessions = sessions
        self._vault = vault
        self._held: dict[tuple[str, Env], StudioSocket] = {}
        # One look at a time for an org in an env: a slow configure of one org never holds another's save.
        self._looking: dict[tuple[str, Env], asyncio.Lock] = {}

    async def reconcile(self) -> None:
        """Hold every Studio agent of both envs as the database says now, and let go of what it no longer says."""
        for env in Env:
            async with self._sessions() as session:
                kept = await StudioAgentRepository(session).list_newest(env, running=True)
            orgs = {agent.org for agent in kept} | {org for org, held_in in self._held if held_in is env}
            for org in sorted(orgs):
                with survive("holding an org's Studio agents", f"{org} in {env.value}"):
                    await self.refresh(org, env)

    async def refresh(self, org: str, env: Env) -> None:
        """Hold the org's Studio agents in the env as their newest releases say."""
        async with self._looking.setdefault((org, env), asyncio.Lock()):
            async with self._sessions() as session:
                kept = await StudioAgentRepository(session).list_newest(env, org=org, running=True)
            wanted = {agent.name: definitions.parse(agent.definition) for agent in kept}
            socket = self._held.get((org, env))
            if not wanted:
                if socket is not None:
                    del self._held[(org, env)]
                    await socket.close()
                return
            if socket is None:
                socket = StudioSocket(self._sockets, self._sessions, self._vault, self.fetcher, org, env)
                await socket.open()
                self._held[(org, env)] = socket
            await self._hold(socket, wanted)

    async def close(self) -> None:
        """Let every socket go."""
        for socket in list(self._held.values()):
            await socket.close()
        self._held.clear()

    async def _hold(self, socket: StudioSocket, wanted: dict[str, Definition]) -> None:
        socket.forget_secrets()
        for slug in set(socket.agents) - set(wanted):
            await socket.let_go(slug)
        for slug, definition in wanted.items():
            if socket.agents.get(slug) != definition and not await socket.hold(slug, definition):
                logger.warning("studio %s/%s is not held as its newest release says: asked again", socket.org, slug)
