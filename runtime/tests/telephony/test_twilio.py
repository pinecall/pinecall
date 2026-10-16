"""Tests for Twilio's REST by hand: every page read, its sentence on a refusal, the two hosts."""

import httpx
import pytest

from pinecall_runtime.exceptions import UpstreamError, ValidationError
from pinecall_runtime.telephony.schemas import TwilioAccount
from pinecall_runtime.telephony.service.twilio import Twilio, origination_uri, termination_host, verify
from tests.fakes.twilio import Twilio as FakeTwilio


def a_client(fake: FakeTwilio) -> tuple[httpx.AsyncClient, Twilio]:
    """The fake account's REST API over a client on its transport."""
    http = httpx.AsyncClient(transport=fake.transport())
    return http, Twilio(http, fake.account_sid, fake.user, fake.secret)


async def test_a_listing_longer_than_a_page_is_read_whole() -> None:
    fake = FakeTwilio(page_size=2)
    for last in range(5):
        fake.owns(f"+1555010010{last}")
    http, client = a_client(fake)
    async with http:
        numbers = await client.numbers()
    assert sorted(number.phone_number for number in numbers) == sorted(f"+1555010010{last}" for last in range(5))


async def test_a_wrong_pair_is_not_verified_and_a_right_one_is() -> None:
    fake = FakeTwilio()
    http, client = a_client(fake)
    async with http:
        assert await client.verified()
        assert not await Twilio(http, fake.account_sid, fake.user, "not the secret").verified()


async def test_twilios_own_sentence_reaches_the_person_on_a_refusal() -> None:
    fake = FakeTwilio()
    http, client = a_client(fake)
    async with http:
        with pytest.raises(UpstreamError, match="Twilio: no trunk"):
            await client.trunk("TK" + "0" * 32)


def test_the_origination_uri_and_the_termination_host_are_derived_from_the_domain() -> None:
    assert origination_uri("box.test") == "sip:box.test:5060;transport=udp"
    host = termination_host("box.test", "AC" + "f" * 24 + "12345678")
    assert host == "box-test-12345678.pstn.twilio.com"


async def test_a_pair_twilio_refuses_is_refused_in_our_words_and_the_right_one_passes() -> None:
    """The pair is tried against Twilio before it is kept: a wrong secret is refused in one sentence."""
    fake = FakeTwilio()
    right = TwilioAccount.model_validate({"account_sid": fake.account_sid, "user": fake.user, "secret": fake.secret})
    async with httpx.AsyncClient(transport=fake.transport()) as http:
        with pytest.raises(ValidationError, match="Twilio refused"):
            await verify(http, right.model_copy(update={"secret": "not it"}))
        await verify(http, right)
