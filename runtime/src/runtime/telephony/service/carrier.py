"""What a carrier account is to the box, whatever its kind, and what the box is to a carrier: its names."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, Self

import httpx

from runtime.enums import Channel, Env, RouteOrigin
from runtime.exceptions import ServiceUnavailable
from runtime.telephony.models import CarrierKind, Route
from runtime.telephony.service import fence
from runtime.telephony.service.fence import Fenced
from runtime.telephony.service.networks import NOTHING_ASKED, Standing
from runtime.wire.worker import LegTrunk

NO_DOMAIN = "this box has no PINECALL_DOMAIN: a carrier has nowhere to send a call"
# livekit-sip listens here, and the fence opens it to the carrier alone.
SIP_PORT = 5060


# Built once by the entrypoint from the process's settings: no use case reads a setting by itself.
@dataclass(frozen=True, slots=True)
class SipNames:
    """What the box is to a carrier: its name, each env's SIP name, and two things its operator chose."""

    domain: str | None
    sip_domains: Mapping[Env, str | None]
    # Whether a number an org hooks itself waits for the operator's word (PINECALL_APPROVE_HOOKED).
    approve_hooked: bool = False
    # LiveKit's secret, which both envs' clusters share: the hand-over trunk's pair is drawn from it.
    livekit_secret: str | None = None

    def get_domain(self) -> str:
        """The box's name, or ServiceUnavailable: a carrier has nowhere to send a call."""
        if not self.domain:
            raise ServiceUnavailable(NO_DOMAIN)
        return self.domain

    def get_sip_domain(self, env: Env) -> str:
        """The name a carrier sends that env's calls to, or ServiceUnavailable: it has none."""
        name = self.sip_domains.get(env)
        if not name:
            raise ServiceUnavailable(NO_DOMAIN)
        return name

    def origination_of(self, env: Env) -> str:
        """The SIP URI a carrier's trunk sends that env's calls to."""
        return origination_uri(self.get_sip_domain(env))


def origination_uri(domain: str) -> str:
    """The SIP URI a carrier's trunk sends this box's calls to."""
    return f"sip:{domain}:{SIP_PORT};transport=udp"


# A WhatsApp route is Meta's: through an account, the number is the one the org's WhatsApp Business
# account is, as Meta names it, never a phone number typed with `--channel whatsapp`.
NOT_A_WHATSAPP_ACCOUNT = (
    "a WhatsApp number comes through the org's WhatsApp Business account: `pinecall carriers add whatsapp` first, "
    "then import the number that account is"
)


# A row is read as strictly as it is written: a field that is not there, or not text, is no account.
def read_text(kept: Mapping[str, object], name: str) -> str:
    """A field an account cannot be without; ValueError when it is missing, empty or not text."""
    value = kept.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is missing")
    return value


def read_optional_text(kept: Mapping[str, object], name: str) -> str | None:
    """A field an account may leave out; ValueError when it is there and not text."""
    value = kept.get(name)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} is not text")
    return value or None


@dataclass(frozen=True, slots=True)
class Owned:
    """A number an account owns at its carrier, and the name it has there."""

    number: str
    name: str


# What is said is what is done, by construction: a dry run says the list, a hook runs it in order,
# and a step that stands writes nothing. Until 2026-11 the sentences and the writes were two functions
# with their own conditions, and three writes had no sentence.
@dataclass(frozen=True, slots=True)
class Step:
    """One thing a hook does: its sentence, whether it stands already, and its write."""

    says: str
    stands: bool
    write: Callable[[], Awaitable[None]]

    def say(self, *, done: bool) -> str:
        """The sentence with how the step stands: there already, done just now, or still to do."""
        return f"{self.says}: {'stands' if self.stands else 'done' if done else 'to do'}"


@dataclass(frozen=True, slots=True)
class Outbound:
    """How an account stands to place a call: one sentence a step, whether every step stands, where it is dialled."""

    steps: list[str]
    ready: bool
    address: str | None = None
    trunk: str | None = None


# Three kinds of account answer the same questions differently: each kind is a module whose class
# subclasses this and answers them, and nothing outside asks which kind an account is. Until 2026-11
# the kind was asked again at each of 29 sites, and two of them had come to disagree.
class Carrier(Protocol):
    """One account of an org at an outside party that holds its numbers."""

    kind: ClassVar[CarrierKind]
    # What a sentence calls the party: "Twilio", "your PBX", "Meta".
    name: ClassVar[str]
    # The box drives its API: it lists, points and provisions numbers through it.
    has_api: ClassVar[bool]

    # The org whose account it is, and what the org calls it.
    org: str
    label: str

    @property
    def id(self) -> str:
        """The account's own id: Twilio's SID, the peer's username, Meta's phone number id."""
        ...

    @classmethod
    def read(cls, org: str, account: Mapping[str, object], outbound: Mapping[str, object] | None) -> Self:
        """The account out of what a row seals or a body brings; ValueError when it is not one of this kind."""
        ...

    def dump(self) -> dict[str, Any]:
        """The account as its row seals it."""
        ...

    def keep_from(self, was: object) -> Self:
        """This account with what the box made on the one it replaces: brought again, an account keeps it."""
        ...

    async def verify(self, http: httpx.AsyncClient) -> None:
        """Refuse an account its party does not open with what was given."""
        ...

    def calling_networks(self) -> tuple[str, ...] | None:
        """The networks the account says it calls from, for the operator to approve; None when it names none."""
        ...

    def fence(self, number: str, standing: Standing) -> Fenced:
        """Who the SFU admits a number of the account from, with what is approved now."""
        ...

    def list_missing_to_dial(self) -> list[str]:
        """What the account lacks before a call can go out through it, one sentence each."""
        ...

    def leg_trunk(self, shown: str) -> LegTrunk:
        """How a leg through the account is dialled, showing the number; Conflict naming what is missing."""
        ...

    async def list_owned(self, http: httpx.AsyncClient) -> list[Owned]:
        """The numbers the account owns, as its party lists them; none where nobody can list them."""
        ...

    async def check_number(self, http: httpx.AsyncClient, channel: Channel, number: str) -> None:
        """Refuse a number that cannot answer on the channel through this account."""
        ...

    async def survey_hook(
        self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env, *, move: bool
    ) -> list[Step]:
        """What pointing a phone number of the account at the env takes at its party, read before any write."""
        ...

    async def is_pointed_here(self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env) -> bool | None:
        """Whether its party sends the number to the env now; None where nobody can ask."""
        ...

    async def survey_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> Outbound:
        """How the account stands to place a call, nothing written."""
        ...

    async def provision_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> tuple[Outbound, Self]:
        """Make the account dialable; what was done, and the account as it stands after, to be sealed."""
        ...


# An imported number whose account is gone had Twilio's networks for a fence until 2026-11: a number
# with no account read the same whether it never had one or lost it, so a SIP peer's number lost its
# pair and its networks with its account and was admitted from Twilio's edges instead.
def fence_route(route: Route, account: Carrier | None, standings: Mapping[str, Standing]) -> Fenced:
    """The fence a routed phone number has now: its account's, its own, or none while nothing vouches for it."""
    if account is not None:
        return account.fence(route.number, standings.get(account.id, NOTHING_ASKED))
    if route.origin is RouteOrigin.imported:
        return Fenced(None, orphaned=True)
    standing = standings.get(route.number, NOTHING_ASKED)
    return fence.fence_unaccounted(route.org, route.number, route.via, route.networks, standing)
