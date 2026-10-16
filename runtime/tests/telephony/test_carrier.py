"""What an account is to telephony: the networks it is fenced to, where it is dialled, its API."""

import httpx
import pytest

from pinecall_runtime.exceptions import Conflict, ValidationError
from pinecall_runtime.telephony.schemas import Termination, TwilioAccount, WhatsappAccount
from pinecall_runtime.telephony.service import accounts
from pinecall_runtime.telephony.service.accounts import CarrierAccount
from pinecall_runtime.telephony.service.catalog import known_carrier
from pinecall_runtime.telephony.service.fence import (
    TWILIO_SIGNALLING,
    declared_networks,
    dialled_of,
    fence_of,
    missing_to_dial,
)
from pinecall_runtime.telephony.service.twilio import Twilio
from tests.fakes.idp import a_sid
from tests.fakes.meta import Graph
from tests.telephony.conftest import PEER_NETWORK, a_peer

A_NUMBER = "+59829001199"

A_TERMINATION = Termination.model_validate(
    {"host": "box-1234.pstn.twilio.com", "username": "pinecall-org-a", "password": "minted here"}
)


def a_twilio(*, outbound: Termination | None = None) -> CarrierAccount:
    """The org's Twilio account, dialable once a termination was made."""
    account = TwilioAccount.model_validate(
        {"account_sid": a_sid("AC", 1), "user": a_sid("SK", 1), "secret": "the key's secret"}
    )
    return CarrierAccount(org="org_a", account=account, outbound=outbound)


def a_whatsapp() -> CarrierAccount:
    """The org's WhatsApp number at Meta."""
    return CarrierAccount(
        org="org_a",
        account=WhatsappAccount.model_validate({"phone_number_id": "1171462246041897", "access_token": "a token"}),
    )


def test_a_twilio_number_and_one_with_no_account_are_fenced_to_twilios_edges() -> None:
    for brought in (a_twilio(), None):
        fence = fence_of("org_a", A_NUMBER, brought, None, None)
        assert fence is not None
        assert (fence.trunk, fence.networks) == ("org_a", TWILIO_SIGNALLING)


def test_a_number_via_a_catalog_carrier_is_fenced_to_that_carriers_networks() -> None:
    fence = fence_of("org_a", A_NUMBER, None, "telnyx", None)
    assert fence is not None
    assert (fence.trunk, fence.networks) == ("org_a:telnyx", known_carrier("telnyx").networks)


def test_a_peer_is_fenced_to_its_approved_networks_with_its_pair_and_to_none_before() -> None:
    peer = CarrierAccount("org_a", a_peer())
    assert fence_of("org_a", A_NUMBER, peer, None, ()) is None
    fence = fence_of("org_a", A_NUMBER, peer, None, (PEER_NETWORK,))
    assert fence is not None
    assert (fence.trunk, fence.networks, fence.username) == ("org_a:pbx", (PEER_NETWORK,), "pbx")
    assert declared_networks(peer) == (PEER_NETWORK,)
    assert declared_networks(a_twilio()) is None


def test_a_hooked_number_with_networks_is_a_fence_of_its_own_once_approved() -> None:
    assert fence_of("org_a", A_NUMBER, None, None, ()) is None
    fence = fence_of("org_a", A_NUMBER, None, None, ("45.60.13.7/32",))
    assert fence is not None
    assert (fence.trunk, fence.networks) == (f"org_a:{A_NUMBER}", ("45.60.13.7/32",))


def test_a_whatsapp_number_is_on_no_trunk() -> None:
    with pytest.raises(ValidationError, match="on no SIP trunk"):
        fence_of("org_a", A_NUMBER, a_whatsapp(), None, None)


def test_what_each_kind_lacks_to_dial_out() -> None:
    assert "POST /v1/carrier/outbound" in missing_to_dial(a_twilio())[0]
    assert "outbound_host" in missing_to_dial(CarrierAccount("org_a", a_peer()))[0]
    assert "places no call" in missing_to_dial(a_whatsapp())[0]
    dialable = A_TERMINATION
    assert missing_to_dial(a_twilio(outbound=dialable)) == []


def test_a_call_goes_to_twilios_termination_or_to_the_peers_host() -> None:
    dialable = A_TERMINATION
    through_twilio = dialled_of(a_twilio(outbound=dialable))
    assert (through_twilio.hostname, through_twilio.transport) == (dialable.host, "auto")
    peer = CarrierAccount("org_a", a_peer(outbound_host="sip.carrier.example", outbound_transport="tls"))
    through_peer = dialled_of(peer)
    assert (through_peer.hostname, through_peer.transport, through_peer.username) == (
        "sip.carrier.example",
        "tls",
        "pbx",
    )
    with pytest.raises(Conflict, match="outbound_host"):
        dialled_of(CarrierAccount("org_a", a_peer()))


async def test_only_twilio_has_an_api_the_box_drives_and_only_meta_is_whatsapp() -> None:
    async with httpx.AsyncClient() as http:
        assert isinstance(accounts.control_of(http, a_twilio()), Twilio)
        assert accounts.control_of(http, CarrierAccount("org_a", a_peer())) is None
        assert accounts.control_of(http, a_whatsapp()) is None
        await accounts.verify_account(http, a_peer())
    assert accounts.meta_of(a_whatsapp()) is not None
    assert accounts.meta_of(a_twilio()) is None


async def test_a_whatsapp_number_is_kept_only_when_meta_opens_it_with_the_token() -> None:
    account = a_whatsapp().account
    assert isinstance(account, WhatsappAccount)
    graph = Graph()
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph.answer)) as http:
        await accounts.verify_account(http, account)
        graph.refusal = (401, "Invalid OAuth access token - Cannot parse access token")
        with pytest.raises(ValidationError, match="Meta does not open WhatsApp number 1171"):
            await accounts.verify_account(http, account)
