"""What an account is to telephony: who may call the box with it, and where it is dialled."""

from dataclasses import dataclass
from typing import assert_never

from pinecall_runtime.exceptions import Conflict, ValidationError
from pinecall_runtime.telephony.schemas import (
    SipPeer,
    Transport,
    TwilioAccount,
    WhatsappAccount,
)
from pinecall_runtime.telephony.service import networks
from pinecall_runtime.telephony.service.accounts import CarrierAccount
from pinecall_runtime.telephony.service.catalog import BOX_CARRIER, known_carrier

# Twilio's signalling edges, from the catalog: the fence of every Twilio number on the SFU, and the
# set the cloud firewall opens 5060 to. A test holds them equal.
TWILIO_SIGNALLING: tuple[str, ...] = known_carrier(BOX_CARRIER).networks


@dataclass(frozen=True, slots=True)
class Fence:
    """Who the SFU admits a number's INVITE from: one trunk per fence."""

    trunk: str
    networks: tuple[str, ...]
    username: str = ""
    password: str = ""


@dataclass(frozen=True, slots=True)
class Dialled:
    """Where a call through the account is sent: the host, its transport and the pair."""

    hostname: str
    transport: Transport
    username: str
    password: str


# A trunk that lists no address admits every source: a fence with none approved is no trunk at all.
# `via` is the catalog carrier a number with no account comes through; `own` the approved networks
# of the peer, or of a number hooked with networks of its own (None: it named none).
def fence_of(
    org: str, number: str, carrier: CarrierAccount | None, via: str | None, own: tuple[str, ...] | None
) -> Fence | None:
    """Who the SFU admits the number from, or None until the operator approves a network of it."""
    if carrier is None:
        if own is not None:
            return Fence(trunk=f"{org}:{number}", networks=own) if own else None
        kind = via or BOX_CARRIER
        trunk = org if kind == BOX_CARRIER else f"{org}:{kind}"
        return Fence(trunk=trunk, networks=known_carrier(kind).networks)
    match carrier.account:
        case TwilioAccount():
            return Fence(trunk=org, networks=TWILIO_SIGNALLING)
        case SipPeer():
            peer = carrier.account
            if not own:
                return None
            return Fence(trunk=f"{org}:{peer.username}", networks=own, username=peer.username, password=peer.password)
        case WhatsappAccount():
            raise ValidationError(f"{carrier.id} is a WhatsApp number: it is on no SIP trunk")


def declared_networks(carrier: CarrierAccount) -> tuple[str, ...] | None:
    """The networks a peer says it calls from, for the operator to approve; None for the others."""
    match carrier.account:
        case SipPeer():
            return tuple(carrier.account.addresses)
        case TwilioAccount() | WhatsappAccount():
            return None


def own_networks(
    declared: tuple[str, ...] | None, approved: tuple[str, ...]
) -> tuple[tuple[str, ...] | None, tuple[str, ...]]:
    """Of the networks named for a fence, the approved ones (None: it named none) and the rest."""
    if declared is None:
        return None, ()
    named = tuple(networks.network_text(network) for network in declared)
    return tuple(n for n in named if n in approved), tuple(n for n in named if n not in approved)


def missing_to_dial(carrier: CarrierAccount) -> list[str]:
    """What the account lacks before a call can go out through it, one sentence each."""
    account = carrier.account
    match account:
        case TwilioAccount():
            return (
                []
                if carrier.outbound
                else [
                    f"the org's account {carrier.id} cannot place a call yet: POST /v1/carrier/outbound provisions it"
                ]
            )
        case SipPeer():
            if account.outbound_host:
                return []
            return [
                f"SIP peer {carrier.id} declared no outbound_host: the networks a peer calls FROM are not an "
                f"address it takes calls AT"
            ]
        case WhatsappAccount():
            return [f"{carrier.id} is a WhatsApp number: it places no call"]
    assert_never(account)


def dialled_of(carrier: CarrierAccount) -> Dialled:
    """Where a call through the account goes; Conflict naming what is missing."""
    missing = missing_to_dial(carrier)
    if missing:
        raise Conflict(missing[0])
    account = carrier.account
    if isinstance(account, WhatsappAccount):
        raise Conflict(f"{carrier.id} is a WhatsApp number: it places no call")
    if isinstance(account, SipPeer):
        return Dialled(
            hostname=str(account.outbound_host),
            transport=account.outbound_transport,
            username=account.outbound_username or account.username,
            password=account.outbound_password or account.password,
        )
    termination = carrier.outbound
    if termination is None:
        raise Conflict(
            f"the org's account {carrier.id} cannot place a call yet: POST /v1/carrier/outbound provisions it"
        )
    return Dialled(
        hostname=termination.host, transport="auto", username=termination.username, password=termination.password
    )
