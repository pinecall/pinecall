"""What an account is to telephony, whatever its kind: the networks it is fenced to, where it is dialled, its API."""

import httpx
import pytest

from runtime.exceptions import Conflict, ValidationError
from runtime.telephony.service.carrier import Carrier
from runtime.telephony.service.catalog import get_known
from runtime.telephony.service.fence import TWILIO_SIGNALLING, fence_unaccounted
from runtime.telephony.service.networks import NOTHING_ASKED, Standing
from runtime.telephony.service.sip_peer import SipPeer
from runtime.telephony.service.twilio_carrier import Termination, TwilioCarrier
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from tests.fakes.idp import a_sid
from tests.fakes.meta import Graph

ORG = "org_a"
A_NUMBER = "+59829001199"
SHOWN = "+15550100133"
# Public, and narrow enough for the operator to approve.
PEER_NETWORK = "45.60.12.0/24"
A_TERMINATION = Termination(host="box-1234.pstn.twilio.com", username="pinecall-org-a", password="minted here")


def a_twilio(*, outbound: Termination | None = None) -> TwilioCarrier:
    """The org's Twilio account, dialable once a termination was made."""
    return TwilioCarrier(
        org=ORG, account_sid=a_sid("AC", 1), user=a_sid("SK", 1), secret="the key's secret", outbound=outbound
    )


def a_peer(outbound_host: str | None = None) -> SipPeer:
    """A PBX of the org's that calls from its office's network."""
    return SipPeer(
        org=ORG,
        username="pbx",
        password="a peer's password",
        addresses=(PEER_NETWORK,),
        outbound_host=outbound_host,
        outbound_transport="tls" if outbound_host else "auto",
    )


def a_whatsapp() -> WhatsappNumber:
    """The org's WhatsApp number at Meta."""
    return WhatsappNumber(org=ORG, phone_number_id="1171462246041897", access_token="a token")


EVERY_KIND: list[Carrier] = [a_twilio(), a_peer(), a_whatsapp()]


@pytest.mark.parametrize("account", EVERY_KIND, ids=lambda account: account.kind)
def test_every_kind_reads_back_what_its_row_seals(account: Carrier) -> None:
    """What a kind dumps, the same kind reads: the row is the account."""
    sealed = account.dump()
    assert type(account).read(ORG, sealed["account"], sealed["outbound"]) == account


def test_a_twilio_number_and_one_with_no_account_are_fenced_to_twilios_edges() -> None:
    fenced = a_twilio().fence(A_NUMBER, NOTHING_ASKED).fence
    unaccounted = fence_unaccounted(ORG, A_NUMBER, None, (), NOTHING_ASKED).fence
    for fence in (fenced, unaccounted):
        assert fence is not None
        assert (fence.trunk, fence.networks) == (ORG, TWILIO_SIGNALLING)


def test_a_number_via_a_catalog_carrier_is_fenced_to_that_carriers_networks() -> None:
    fence = fence_unaccounted(ORG, A_NUMBER, "telnyx", (), NOTHING_ASKED).fence
    assert fence is not None
    assert (fence.trunk, fence.networks) == ("org_a:telnyx", get_known("telnyx").networks)


def test_a_peer_is_fenced_to_its_approved_networks_with_its_pair_and_to_none_before() -> None:
    peer = a_peer()
    waiting = peer.fence(A_NUMBER, NOTHING_ASKED)
    assert (waiting.fence, waiting.waiting) == (None, (PEER_NETWORK,))
    fence = peer.fence(A_NUMBER, Standing(approved=(PEER_NETWORK,))).fence
    assert fence is not None
    assert (fence.trunk, fence.networks, fence.username) == ("org_a:pbx", (PEER_NETWORK,), "pbx")
    assert peer.calling_networks() == (PEER_NETWORK,)
    assert a_twilio().calling_networks() is None


def test_a_hooked_number_with_networks_is_a_fence_of_its_own_once_approved() -> None:
    hooked = ("45.60.13.7/32",)
    assert fence_unaccounted(ORG, A_NUMBER, None, hooked, NOTHING_ASKED).fence is None
    fence = fence_unaccounted(ORG, A_NUMBER, None, hooked, Standing(approved=hooked)).fence
    assert fence is not None
    assert (fence.trunk, fence.networks) == (f"org_a:{A_NUMBER}", hooked)


def test_a_whatsapp_number_is_on_no_trunk() -> None:
    with pytest.raises(ValidationError, match="on no SIP trunk"):
        a_whatsapp().fence(A_NUMBER, NOTHING_ASKED)


def test_what_each_kind_lacks_to_dial_out() -> None:
    assert "POST /v1/carrier/outbound" in a_twilio().list_missing_to_dial()[0]
    assert "outbound_host" in a_peer().list_missing_to_dial()[0]
    assert "places no call" in a_whatsapp().list_missing_to_dial()[0]
    assert a_twilio(outbound=A_TERMINATION).list_missing_to_dial() == []


def test_a_call_goes_to_twilios_termination_or_to_the_peers_host() -> None:
    through_twilio = a_twilio(outbound=A_TERMINATION).leg_trunk(SHOWN)
    assert (through_twilio.hostname, through_twilio.transport, through_twilio.shown) == (
        A_TERMINATION.host,
        "auto",
        SHOWN,
    )
    through_peer = a_peer(outbound_host="sip.carrier.example").leg_trunk(SHOWN)
    assert (through_peer.hostname, through_peer.transport, through_peer.username) == (
        "sip.carrier.example",
        "tls",
        "pbx",
    )
    with pytest.raises(Conflict, match="outbound_host"):
        a_peer().leg_trunk(SHOWN)


def test_only_twilio_has_an_api_the_box_drives() -> None:
    assert [account.has_api for account in EVERY_KIND] == [True, False, False]


async def test_a_peer_is_asked_nothing_before_its_first_call() -> None:
    async with httpx.AsyncClient() as http:
        await a_peer().verify(http)


async def test_a_whatsapp_number_is_kept_only_when_meta_opens_it_with_the_token() -> None:
    graph = Graph()
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph.answer)) as http:
        await a_whatsapp().verify(http)
        graph.refusal = (401, "Invalid OAuth access token - Cannot parse access token")
        with pytest.raises(ValidationError, match="Meta does not open WhatsApp number 1171"):
            await a_whatsapp().verify(http)
