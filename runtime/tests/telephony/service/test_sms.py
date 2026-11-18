"""SMS through Twilio: a number's messages pointed at the box, the address that proves a post, what is posted."""

import httpx
import pytest
from cryptography.fernet import Fernet

from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, Forbidden, UpstreamError, ValidationError
from runtime.kit.crypto import Vault
from runtime.telephony.repository import RouteRepository
from runtime.telephony.service import accounts, number_hook, numbers, sms
from runtime.telephony.service.number_hook import NumberImport, Plan
from runtime.telephony.service.twilio import TwilioAccount
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from tests.conftest import needs_the_database
from tests.fakes.twilio import Twilio
from tests.telephony.conftest import Line, a_number

VAULT = Vault(Fernet.generate_key().decode())


async def imported(line: Line, wanted: NumberImport) -> Plan:
    """The import, in one transaction as the endpoint runs it."""
    async with line.sessions.begin() as session:
        return await number_hook.import_number(session, line.vault, line.http, line.livekits, line.names, wanted)


# ── the address that proves a post ──


def test_the_address_twilio_posts_to_is_the_numbers_own_and_no_other_number_opens_it() -> None:
    """The mark in the address is the vault's on that number: another number's, or one made up, is refused."""
    url = sms.sms_hook_url(VAULT, "https://box.example", "+15550100000")
    assert url.startswith("https://box.example/v1/sms/twilio/")
    assert sms.sms_status_url(VAULT, "https://box.example", "+15550100000") == f"{url}/status"
    mark = url.rsplit("/", 1)[1]
    sms.refuse_another_mark(VAULT, "+15550100000", mark)
    for number, word in (("+15550100001", mark), ("+15550100000", "a guess")):
        with pytest.raises(Forbidden):
            sms.refuse_another_mark(VAULT, number, word)
    with pytest.raises(Forbidden):
        sms.refuse_another_mark(Vault(Fernet.generate_key().decode()), "+15550100000", mark)


# ── what Twilio posts ──


def test_a_message_twilio_posts_is_read_as_who_wrote_to_which_number_and_what() -> None:
    message = sms.read_message(
        {
            "To": "+15550100000",
            "From": "+59899000001",
            "Body": "quiero un turno",
            "MessageSid": "SM9",
            "AccountSid": "AC1",
        }
    )
    assert (message.number, message.caller, message.text, message.message_id) == (
        "+15550100000",
        "+59899000001",
        "quiero un turno",
        "SM9",
    )
    assert (message.channel, message.phone_number_id, message.signed_for) == (Channel.sms, "AC1", None)
    assert sms.read_message({"To": "+15550100000", "From": "+59899000001", "Body": ""}).text is None


def test_a_receipt_twilio_posts_names_the_boxs_number_the_contact_and_why_it_failed() -> None:
    """Twilio's `From` is the box's number on a receipt; a reply nobody will get carries Twilio's code."""
    posted = {"From": "+15550100000", "To": "+59899000001", "MessageSid": "SM9", "MessageStatus": "delivered"}
    receipt = sms.read_receipt(posted)
    assert (receipt.number, receipt.caller, receipt.status, receipt.error) == (
        "+15550100000",
        "+59899000001",
        "delivered",
        None,
    )
    assert receipt.channel is Channel.sms
    failed = sms.read_receipt({**posted, "MessageStatus": "undelivered", "ErrorCode": "30034"})
    assert (failed.status, failed.error) == ("undelivered", "Twilio error 30034")


# ── a number's messages pointed here ──


@needs_the_database
async def test_a_number_that_answers_the_phone_also_answers_sms_and_twilio_posts_its_messages_here(
    line: Line,
) -> None:
    """The same number, a second route: Twilio is told where its messages go, and its phone route is as it was."""
    number = a_number()
    await line.brought()
    sid = line.twilio.owns(number)
    await imported(line, NumberImport(line.scope(), "recepcion", number))
    trunk = list(line.trunk(line.org).numbers)
    plan = await imported(line, NumberImport(line.scope(), "front-desk", number, channel=Channel.sms))
    here = sms.sms_hook_url(line.vault, f"https://{line.names.get_domain()}", number)
    assert line.twilio.sms_urls[sid] == here
    assert plan.steps == [
        f"twilio: {number}'s messages posted to this box: done",
        f"route: {number} to front-desk in the production: done",
    ]
    async with line.sessions() as session:
        both = await RouteRepository(session).list_at(line.org, number)
        assert [(one.route.channel, one.route.agent, one.route.account) for one in both] == [
            (Channel.phone, "recepcion", line.twilio.account_sid),
            (Channel.sms, "front-desk", line.twilio.account_sid),
        ]
        by_sms = await numbers.get_number(session, line.org, number, Env.production, Channel.sms)
        account = await sms.sms_account_of(session, line.vault, by_sms)
        assert account is not None and account.account_sid == line.twilio.account_sid
    assert list(line.trunk(line.org).numbers) == trunk == [number]
    again = await imported(line, NumberImport(line.scope(), "front-desk", number, channel=Channel.sms))
    assert again.steps[0] == f"twilio: {number}'s messages posted to this box: stands"


@needs_the_database
async def test_messages_that_go_to_another_service_are_taken_only_when_told_to_move(line: Line) -> None:
    """A number whose SMS another service answers is not taken by the way: the refusal says where they go."""
    number = a_number()
    await line.brought()
    sid = line.twilio.owns(number)
    line.twilio.sms_urls[sid] = "https://another.example/sms"
    wanted = NumberImport(line.scope(), "front-desk", number, channel=Channel.sms)
    with pytest.raises(Conflict, match="go to https://another\\.example/sms now"):
        await imported(line, wanted)
    assert line.twilio.sms_urls[sid] == "https://another.example/sms"
    async with line.sessions.begin() as session:
        moving = NumberImport(line.scope(), "front-desk", number, channel=Channel.sms, move=True)
        await number_hook.import_number(session, line.vault, line.http, line.livekits, line.names, moving)
    assert line.twilio.sms_urls[sid].startswith(f"https://{line.names.get_domain()}/v1/sms/twilio/")


@needs_the_database
async def test_sms_comes_through_a_twilio_account_and_through_nothing_else(line: Line) -> None:
    """A number hooked by the org, or one of a WhatsApp account, has no API to point its messages with."""
    number = a_number()
    with pytest.raises(ValidationError, match="it is not hooked"):
        await imported(line, NumberImport(line.scope(), "front-desk", number, channel=Channel.sms, hooked=True))
    async with line.sessions.begin() as session:
        at_meta = WhatsappNumber(org=line.org, phone_number_id="1055", access_token="a token")
        await accounts.put_carrier(session, line.vault, at_meta)
    with pytest.raises(Conflict, match="SMS comes through a Twilio account"):
        await imported(line, NumberImport(line.scope(), "front-desk", number, channel=Channel.sms, account="1055"))


# ── the audio of an MMS ──


def test_an_mms_that_carries_audio_is_a_voice_note_and_any_other_attachment_is_nothing_read() -> None:
    """Audio alone is heard; a picture is dropped, and words beside a picture are the message."""
    posted = {"To": "+15550100000", "From": "+59899000001", "MessageSid": "MM1", "NumMedia": "1"}
    where = "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages/MM1/Media/ME1"
    spoken = sms.read_message({**posted, "MediaUrl0": where, "MediaContentType0": "audio/amr"})
    assert (spoken.kind, spoken.text, spoken.media_id) == ("audio", None, where)
    pictured = sms.read_message({**posted, "MediaUrl0": where, "MediaContentType0": "image/jpeg", "Body": "mira"})
    assert (pictured.kind, pictured.text, pictured.media_id) == ("text", "mira", None)
    assert sms.read_message({**posted, "NumMedia": "0", "Body": "hola"}).media_id is None


async def test_the_audio_of_an_mms_is_fetched_at_twilio_with_the_accounts_pair_and_nowhere_else() -> None:
    """The address comes in the post: it is asked for only when it is Twilio's own, and never when it is long."""
    twilio = Twilio()
    kept = f"/2010-04-01/Accounts/{twilio.account_sid}/Messages/MM1/Media/ME1"
    twilio.media[kept.removeprefix(f"/2010-04-01/Accounts/{twilio.account_sid}")] = (b"#!AMR-some-audio", "audio/amr")
    account = TwilioAccount(twilio.account_sid, twilio.user, twilio.secret)
    async with httpx.AsyncClient(transport=twilio.transport()) as http:
        media = await sms.read_sms_media(http, account, f"https://api.twilio.com{kept}")
        assert (media.data, media.mime_type) == (b"#!AMR-some-audio", "audio/amr")
        for elsewhere in (
            "https://evil.example/audio.amr",
            "http://api.twilio.com/x",
            "https://api.twilio.com.evil.example/x",
        ):
            with pytest.raises(UpstreamError, match="not Twilio's"):
                await sms.read_sms_media(http, account, elsewhere)
