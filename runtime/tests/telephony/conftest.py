"""What the telephony tests share: a PBX of the org's, and the line numbers are hooked through."""

import os
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
from livekit.protocol.sip import SIPDispatchRuleInfo, SIPInboundTrunkInfo
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.config import load_settings
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.redis import LocalSignal
from pinecall_runtime.telephony.schemas import SipPeer, TwilioAccount
from pinecall_runtime.telephony.service import accounts
from tests.conftest import Tenant
from tests.fakes.livekit import Server, per_world
from tests.fakes.meta import Graph, outside
from tests.fakes.twilio import Twilio
from tests.fakes.webhooks import Receiver

# Public, and narrow enough for the operator to approve.
PEER_NETWORK = "45.60.12.0/24"
DOMAIN = "box.test"


def a_peer(**said: object) -> SipPeer:
    """A PBX of the org's that calls from its office's network."""
    return SipPeer.model_validate(
        {"username": "pbx", "password": "a peer's password", "addresses": [PEER_NETWORK], **said}
    )


def a_number() -> str:
    """A number of this test alone: a number is one org's on the whole box."""
    return f"+1555{secrets.randbelow(10**7):07d}"


@dataclass
class Line:
    """The handles a test hooks numbers through, the org, and the fakes outside the box."""

    handles: Handles
    org: str
    twilio: Twilio
    graph: Graph
    # Each env's own LiveKit.
    servers: dict[Env, Server]

    @property
    def sessions(self) -> async_sessionmaker[AsyncSession]:
        """The sessions the services are handed."""
        return self.handles.sessions

    def scope(self, env: Env = Env.production) -> Scope:
        """The org's scope in the env."""
        return Scope(self.org, env)

    def account(self) -> TwilioAccount:
        """The fake account, as the org brings it."""
        return TwilioAccount(account_sid=self.twilio.account_sid, user=self.twilio.user, secret=self.twilio.secret)

    def trunk(self, name: str, env: Env = Env.production) -> SIPInboundTrunkInfo:
        """A trunk on the env's LiveKit, by name."""
        return next(trunk for trunk in self.servers[env].dialled.trunks.values() if trunk.name == name)

    def rules(self, env: Env = Env.production) -> list[str]:
        """The names of the rules on the env's LiveKit."""
        return sorted(rule.name for rule in self.servers[env].dialled.rules.values())

    def rule(self, env: Env) -> SIPDispatchRuleInfo:
        """The org's rule of the env on that env's LiveKit."""
        name = f"{self.org}:{env}"
        return next(rule for rule in self.servers[env].dialled.rules.values() if rule.name == name)

    async def brought(self) -> None:
        """The org brought its Twilio account, its pair tried first as the endpoint does."""
        await accounts.verify_account(self.handles.http, self.account())
        async with self.sessions.begin() as session:
            await accounts.put_carrier(session, self.handles.vault, self.org, self.account())


@pytest.fixture
async def line(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> AsyncIterator[Line]:
    """The tenant's org, a Twilio account nobody brought yet, Meta, a bare LiveKit for each env."""
    twilio, graph, servers = Twilio(), Graph(number=a_number()), per_world()
    settings = load_settings().model_copy(update={"domain": DOMAIN, "sip_domain": None, "sandbox_sip_domain": None})
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    async with httpx.AsyncClient(transport=outside(twilio, graph, Receiver())) as http:
        handles = Handles(settings, vault, http, servers, LocalSignal(), sessions)
        yield Line(handles, tenant.org, twilio, graph, servers)
    for server in servers.values():
        await server.aclose()
