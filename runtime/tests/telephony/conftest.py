"""What the telephony tests share: the org, the fakes outside the box, each env's LiveKit, and the box's names."""

import os
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
from livekit.protocol.sip import SIPDispatchRuleInfo, SIPInboundTrunkInfo
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.enums import Env
from runtime.kit.crypto import Vault
from runtime.livekit import Servers
from runtime.telephony.service import rebuild
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.twilio_carrier import TwilioCarrier
from tests.conftest import Tenant
from tests.fakes.livekit import Server, per_world
from tests.fakes.meta import Graph, outside
from tests.fakes.twilio import Twilio
from tests.fakes.webhooks import Receiver

DOMAIN = "box.test"
# What the entrypoint builds from the settings of a box with a name and no SIP name of its own.
NAMES = SipNames(domain=DOMAIN, sip_domains={Env.production: DOMAIN, Env.sandbox: DOMAIN})


def a_number() -> str:
    """A number of this test alone: a number is one org's on the whole box."""
    return f"+1555{secrets.randbelow(10**7):07d}"


@dataclass
class Line:
    """What a test hooks numbers through: the box's handles, the org, and the fakes outside the box."""

    sessions: async_sessionmaker[AsyncSession]
    vault: Vault
    http: httpx.AsyncClient
    names: SipNames
    org: str
    twilio: Twilio
    graph: Graph
    # Each env's own LiveKit.
    servers: dict[Env, Server]

    @property
    def livekits(self) -> Servers:
        """The servers as the services take them."""
        return self.servers

    def scope(self, env: Env = Env.production) -> Scope:
        """The org's scope in the env."""
        return Scope(self.org, env)

    def account(self) -> TwilioCarrier:
        """The fake account, as the org brings it."""
        return TwilioCarrier(
            org=self.org, account_sid=self.twilio.account_sid, user=self.twilio.user, secret=self.twilio.secret
        )

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
        """The org brought its Twilio account, as the endpoint keeps it: verified, sealed, its trunks following."""
        async with self.sessions.begin() as session:
            await rebuild.bring_carrier(session, self.vault, self.http, self.livekits, self.account())


@pytest.fixture
async def line(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> AsyncIterator[Line]:
    """The tenant's org, a Twilio account nobody brought yet, Meta, a bare LiveKit for each env."""
    twilio, graph, servers = Twilio(), Graph(number=a_number()), per_world()
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    async with httpx.AsyncClient(transport=outside(twilio, graph, Receiver())) as http:
        yield Line(sessions, vault, http, NAMES, tenant.org, twilio, graph, servers)
    for server in servers.values():
        await server.aclose()
