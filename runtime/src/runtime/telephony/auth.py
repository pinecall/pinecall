"""Telephony's dependencies: the keys that open its endpoints, a number loaded, and what its use cases are handed."""

from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import Depends, Query, Request
from starlette.requests import HTTPConnection

from runtime.accounts.models import Org
from runtime.accounts.service import orgs
from runtime.actor import Actor
from runtime.auth import Authenticator, TheOperator
from runtime.enums import Channel, KeyScope
from runtime.exceptions import NotFound
from runtime.handles import TheVault
from runtime.kit.http import read_capped_body
from runtime.kit.text import parse_address
from runtime.postgres import Session, TheBoxSession
from runtime.telephony.models import Route
from runtime.telephony.service import numbers, sms
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.hand_over import AgentsHeld
from runtime.whatsapp import service as whatsapp

NumbersKey = Annotated[Actor, Depends(Authenticator(KeyScope.numbers))]
TalkKey = Annotated[Actor, Depends(Authenticator(KeyScope.talk))]
# A ring is asked about by the fleet alone: whose it is names another org's people.
FleetKey = Annotated[Actor, Depends(Authenticator(KeyScope.fleet))]
# The account an endpoint acts on, when the org holds more than one.
AccountAsked = Annotated[str | None, Query()]
DryRun = Annotated[bool, Query()]


# A worker's actor: its fleet's key, or a tenant's own worker's app key. A fleet asks in its own env
# alone, which the resolver of every key holds (`accounts.service.actor.serve_dispatched`).
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]


# A person or a server acts in the org's own scope of its env: numbers are the org's.
# The channel meant, for a number that answers on more than one.
ChannelAsked = Annotated[Channel | None, Query()]


async def load_number(number: str, actor: NumbersKey, session: Session, channel: ChannelAsked = None) -> Route:
    """The org's number a path names, in the key's env; 404 otherwise, 409 for one on two channels and none named."""
    return await numbers.get_number(session, actor.org, parse_address(number), actor.env, channel)


async def load_number_in_either_env(
    number: str, actor: NumbersKey, session: Session, channel: ChannelAsked = None
) -> Route:
    """The org's number a path names, whichever env it answers in; 404 otherwise, 409 as above."""
    return await numbers.get_number(session, actor.org, parse_address(number), channel=channel)


TheNumber = Annotated[Route, Depends(load_number)]
TheNumberInEitherEnv = Annotated[Route, Depends(load_number_in_either_env)]


# The operator names the org in the query where the path names a number.
async def load_org_asked(org: Annotated[str, Query()], _actor: TheOperator, session: TheBoxSession) -> Org:
    """The org an operator's query names, by id or slug."""
    return await orgs.get_org(session, org)


TheOrgAsked = Annotated[Org, Depends(load_org_asked)]


def check_agent(actor: Actor, agent: str) -> None:
    """Refuse an agent a person's key is not let act for: one they do not see is one that is not there."""
    if actor.person is not None and actor.person.agents and agent not in actor.person.agents:
        raise NotFound(f"agent {agent} is not one this key may act for")


def sip_names_of(connection: HTTPConnection) -> SipNames:
    """What the box is to a carrier, as the lifespan read it from the settings."""
    names: SipNames = connection.state.sip_names
    return names


def agents_held_of(connection: HTTPConnection) -> AgentsHeld:
    """The agents the orgs' apps hold now, as the lifespan handed them in."""
    held: AgentsHeld = connection.state.agents_held
    return held


TheSipNames = Annotated[SipNames, Depends(sip_names_of)]
TheAgentsHeld = Annotated[AgentsHeld, Depends(agents_held_of)]


# Twilio posts a form. The address carries the mark of the number the post names as the box's: the
# one written to for a message, the one written from for a receipt.
async def _form_of(request: Request) -> dict[str, str]:
    body = await read_capped_body(request, sms.LONGEST_POST, "a message Twilio posts")
    return dict(parse_qsl(body.decode(errors="replace"), keep_blank_values=True))


async def read_sms(mark: str, request: Request, vault: TheVault) -> whatsapp.Inbound:
    """The message Twilio posted to the address this box gave it for that number; 403 at any other."""
    message = sms.read_message(await _form_of(request))
    sms.refuse_another_mark(vault, message.number, mark)
    return message


async def read_sms_receipt(mark: str, request: Request, vault: TheVault) -> whatsapp.Receipt:
    """Where a reply stands, as Twilio posted it to the number's own address; 403 at any other."""
    receipt = sms.read_receipt(await _form_of(request))
    sms.refuse_another_mark(vault, receipt.number, mark)
    return receipt


TheSms = Annotated[whatsapp.Inbound, Depends(read_sms)]
TheSmsReceipt = Annotated[whatsapp.Receipt, Depends(read_sms_receipt)]
