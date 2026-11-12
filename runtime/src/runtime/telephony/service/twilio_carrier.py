"""A Twilio account of an org: how its row seals it, and what its API does for a number, a trunk and a call out."""

import secrets
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, ClassVar, Self, override

import httpx

from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, NotFound, UpstreamError, ValidationError
from runtime.telephony.models import CarrierKind
from runtime.telephony.service import twilio
from runtime.telephony.service.carrier import (
    NOT_A_WHATSAPP_ACCOUNT,
    Carrier,
    Outbound,
    Owned,
    SipNames,
    Step,
    read_optional_text,
    read_text,
)
from runtime.telephony.service.fence import TWILIO_SIGNALLING, Fence, Fenced
from runtime.telephony.service.networks import Standing
from runtime.telephony.service.twilio import (
    TERMINATION_SUFFIX,
    Twilio,
    TwilioAccount,
    TwilioNumber,
    TwilioTrunk,
    termination_host,
)
from runtime.wire.worker import LegTrunk

KIND = "twilio"


@dataclass(frozen=True, slots=True)
class Termination:
    """How the box dials out through a Twilio account: the host and the credential it made."""

    host: str
    username: str
    password: str


# The number and the trunk at Twilio as a hook's steps leave them: a step reads what the one before made.
@dataclass(slots=True)
class _At:
    number: TwilioNumber | None
    trunk: TwilioTrunk | None


@dataclass(frozen=True, slots=True)
class _OutboundSurvey:
    """What the account holds today: the trunk, its termination host, the list, the credential."""

    trunk: TwilioTrunk | None
    host: str
    list_name: str
    credential_list: str | None
    username: str
    # Whether the list already holds the org's credential; else one is made and sealed.
    holds: bool
    on_trunk: bool
    steps: list[str]

    @property
    def ready(self) -> bool:
        """Whether nothing is left to write."""
        terminates = self.trunk is not None and self.trunk.domain_name == self.host
        return terminates and self.credential_list is not None and self.holds and self.on_trunk


def read_account(kept: Mapping[str, object]) -> TwilioAccount:
    """The account out of what a row seals; ValueError when it is not a Twilio account."""
    return TwilioAccount(
        account_sid=read_text(kept, "account_sid"),
        user=read_text(kept, "user"),
        secret=read_text(kept, "secret"),
        label=read_optional_text(kept, "label") or "",
    )


# Every field, as the release before 2026-11 wrote it and reads it, refusing one it does not know.
def dump_account(account: TwilioAccount) -> dict[str, Any]:
    """The account as a row seals it."""
    return {
        "kind": KIND,
        "account_sid": account.account_sid,
        "user": account.user,
        "secret": account.secret,
        "label": account.label,
    }


@dataclass(frozen=True, slots=True)
class TwilioCarrier(Carrier):
    """A Twilio account of an org, and the termination provisioning made on it."""

    kind: ClassVar[CarrierKind] = CarrierKind.twilio
    name: ClassVar[str] = "Twilio"
    has_api: ClassVar[bool] = True

    org: str
    account_sid: str
    # An API key SID with its secret, or the account's SID and its auth token.
    user: str
    secret: str
    label: str = ""
    # Written by provisioning: Twilio shows a credential's password once.
    outbound: Termination | None = None

    @property
    @override
    def id(self) -> str:
        """The account's SID."""
        return self.account_sid

    @property
    def account(self) -> TwilioAccount:
        """The account as its API is asked."""
        return TwilioAccount(self.account_sid, self.user, self.secret, self.label)

    @classmethod
    @override
    def read(cls, org: str, account: Mapping[str, object], outbound: Mapping[str, object] | None) -> Self:
        """The account out of what a row seals or a body brings."""
        termination = None
        if outbound is not None:
            termination = Termination(
                host=read_text(outbound, "host"),
                username=read_text(outbound, "username"),
                password=read_text(outbound, "password"),
            )
        read = read_account(account)
        return cls(org, read.account_sid, read.user, read.secret, read.label, termination)

    @override
    def dump(self) -> dict[str, Any]:
        """The account as its row seals it, its termination with it."""
        made = self.outbound
        return {
            "account": dump_account(self.account),
            "outbound": None
            if made is None
            else {"host": made.host, "username": made.username, "password": made.password},
        }

    # The termination stays with the account it was made on: bringing the account again replaces its secret.
    @override
    def keep_from(self, was: object) -> Self:
        """This account with the termination the one it replaces had."""
        return replace(self, outbound=was.outbound) if isinstance(was, TwilioCarrier) else self

    @override
    async def verify(self, http: httpx.AsyncClient) -> None:
        """Refuse a pair Twilio does not open the account with."""
        await twilio.verify(http, self.account)

    @override
    def calling_networks(self) -> tuple[str, ...] | None:
        """None: Twilio calls from its own published edges."""
        return None

    @override
    def fence(self, number: str, standing: Standing) -> Fenced:
        """The org's Twilio trunk, admitted from Twilio's signalling edges."""
        return Fenced(Fence(trunk=self.org, networks=TWILIO_SIGNALLING))

    @override
    def list_missing_to_dial(self) -> list[str]:
        """The termination, until provisioning made one."""
        if self.outbound is not None:
            return []
        return [f"the org's account {self.id} cannot place a call yet: POST /v1/carrier/outbound provisions it"]

    @override
    def leg_trunk(self, shown: str) -> LegTrunk:
        """A leg through the account's termination, with the credential made for the org."""
        made = self.outbound
        if made is None:
            raise Conflict(self.list_missing_to_dial()[0])
        return LegTrunk(
            hostname=made.host, transport="auto", username=made.username, password=made.password, shown=shown
        )

    @override
    async def list_owned(self, http: httpx.AsyncClient) -> list[Owned]:
        """Every number the account owns, every page."""
        owned = await twilio.twilio_of(http, self.account).list_numbers()
        return [Owned(number=number.phone_number, name=number.friendly_name or number.phone_number) for number in owned]

    @override
    async def check_number(self, http: httpx.AsyncClient, channel: Channel, number: str) -> None:
        """A Twilio number answers the phone; whether the account owns it is asked when it is hooked."""
        if channel is Channel.whatsapp:
            raise ValidationError(NOT_A_WHATSAPP_ACCOUNT)

    @override
    async def survey_hook(
        self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env, *, move: bool
    ) -> list[Step]:
        """The trunk that sends the env's calls here, and the number attached to it."""
        api = twilio.twilio_of(http, self.account)
        owned = await api.find_number(number)
        if owned is None:
            raise NotFound(f"{number} is not a number of Twilio account {api.sid}")
        trunk = await api.find_trunk_pointing_at(names.origination_of(env))
        if owned.trunk_sid is not None and (trunk is None or owned.trunk_sid != trunk.sid) and not move:
            where = await api.list_originations(owned.trunk_sid)
            other = await api.get_trunk(owned.trunk_sid)
            raise Conflict(
                f"{number} is on Twilio trunk {other.friendly_name or other.sid} of {api.sid}, pointed at "
                f"{', '.join(where) or 'nowhere'}: "
                "moving it here takes it off there, so say move"
            )
        return _hook_steps(api, _At(owned, trunk), names, number, env)

    @override
    async def is_pointed_here(self, http: httpx.AsyncClient, names: SipNames, number: str, env: Env) -> bool | None:
        """Whether the account's number is on its trunk that sends the env's calls here."""
        api = twilio.twilio_of(http, self.account)
        owned = await api.find_number(number)
        trunk = await api.find_trunk_pointing_at(names.origination_of(env))
        return owned is not None and trunk is not None and owned.trunk_sid == trunk.sid

    @override
    async def survey_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> Outbound:
        """The five things a Twilio account needs to place a call, and which stand."""
        survey = await self._survey_outbound(twilio.twilio_of(http, self.account), names, env)
        return Outbound(steps=survey.steps, ready=survey.ready, address=survey.host)

    @override
    async def provision_outbound(self, http: httpx.AsyncClient, names: SipNames, env: Env) -> tuple[Outbound, Self]:
        """Twilio's termination and a credential of the org's on the trunk; the account with what was made."""
        api = twilio.twilio_of(http, self.account)
        survey = await self._survey_outbound(api, names, env)
        trunk = survey.trunk or await api.make_trunk(names.get_domain(), names.origination_of(env))
        if trunk.domain_name != survey.host:
            await api.terminate_at(trunk.sid, survey.host)
        credential_list = survey.credential_list or await api.make_credential_list(survey.list_name)
        made = self.outbound
        if not survey.holds:
            made = Termination(host=survey.host, username=survey.username, password=secrets.token_urlsafe(24))
            await api.add_credential(credential_list, made.username, made.password)
        elif made is not None and made.host != survey.host:
            # The trunk was given the box's host just now (its name changed): dial where it answers.
            made = replace(made, host=survey.host)
        if not survey.on_trunk:
            await api.attach_credential_list(trunk.sid, credential_list)
        done = Outbound(steps=survey.steps, ready=True, address=survey.host, trunk=trunk.sid)
        return done, replace(self, outbound=made)

    # Read before anything is written, so a plan and a provisioning see the same account.
    async def _survey_outbound(self, api: Twilio, names: SipNames, env: Env) -> _OutboundSurvey:
        origination = names.origination_of(env)
        trunk = await api.find_trunk_pointing_at(origination)
        host = termination_host(names.get_domain(), api.sid)
        # One list per trunk, as the trunk is per account and box; one credential per org on it,
        # so two orgs that brought the same account each dial with their own.
        name = host.removesuffix(TERMINATION_SUFFIX)
        username = f"pinecall-{self.org}".replace("_", "-")
        credential_list = await api.find_credential_list(name)
        holds = credential_list is not None and username in await api.list_usernames_in(credential_list)
        if holds and self.outbound is None:
            raise Conflict(
                f"Twilio account {api.sid} holds the credential {username} on list {name}, whose password this "
                f"box no longer has: "
                "delete that credential in Twilio's console and provision again"
            )
        on_trunk = (
            trunk is not None
            and credential_list is not None
            and credential_list in await api.list_credential_lists_on(trunk.sid)
        )
        terminates = trunk is not None and trunk.domain_name == host
        steps = [
            f"Twilio: a trunk sending calls to {origination}: {'stands' if trunk else 'to do'}",
            f"Twilio: dialled at {host}: {'stands' if terminates else 'to do'}",
            f"Twilio: credential list {name}: {'stands' if credential_list else 'to do'}",
            f"Twilio: the org's credential {username} on it: {'stands' if holds else 'to do'}",
            f"Twilio: the trunk asks for it: {'stands' if on_trunk else 'to do'}",
        ]
        return _OutboundSurvey(trunk, host, name, credential_list, username, holds, on_trunk, steps)


# A purchase costs money and is not undone: a dry run names the number Twilio would sell and buys nothing.
async def survey_purchase(
    http: httpx.AsyncClient, account: TwilioAccount, names: SipNames, env: Env, country: str, area_code: str | None
) -> tuple[str, list[Step]]:
    """The number Twilio would sell on the account, and what buying and pointing it here takes."""
    api = twilio.twilio_of(http, account)
    for_sale = await api.find_for_sale(country, area_code)
    if for_sale is None:
        area = f", area code {area_code}" if area_code else ""
        raise NotFound(f"Twilio has no local voice number for sale in {country.upper()}{area}")
    at = _At(None, await api.find_trunk_pointing_at(names.origination_of(env)))

    async def buy() -> None:
        at.number = await api.buy(for_sale)

    bought = Step(f"Twilio: buy {for_sale} on the box's account", stands=False, write=buy)
    return for_sale, [bought, *_hook_steps(api, at, names, for_sale, env)]


def _hook_steps(api: Twilio, at: _At, names: SipNames, number: str, env: Env) -> list[Step]:
    domain, origination = names.get_domain(), names.origination_of(env)
    owned, trunk = at.number, at.trunk
    on_another = None if owned is None or (trunk is not None and owned.trunk_sid == trunk.sid) else owned.trunk_sid
    on_it = owned is not None and trunk is not None and owned.trunk_sid == trunk.sid

    async def make_trunk() -> None:
        at.trunk = await api.make_trunk(domain, origination)

    async def detach() -> None:
        if at.number is not None and on_another is not None:
            await api.detach(on_another, at.number.sid)

    async def attach() -> None:
        if at.number is None or at.trunk is None:
            raise UpstreamError(f"Twilio: {number} or its trunk is not there to attach", vendor=twilio.VENDOR)
        await api.attach(at.trunk.sid, at.number.sid)

    steps = [Step(f"Twilio: a trunk sending calls to {origination}", stands=trunk is not None, write=make_trunk)]
    if on_another is not None:
        steps.append(Step(f"Twilio: {number} off trunk {on_another}", stands=False, write=detach))
    steps.append(Step(f"Twilio: {number} attached to it", stands=on_it, write=attach))
    return steps
