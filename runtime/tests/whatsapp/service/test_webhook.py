"""Tests for Meta's webhook: the handshake, the signature of the box's app and of an org's own, a body's messages."""

import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.exceptions import Forbidden, ServiceUnavailable
from runtime.kit.crypto import Vault
from runtime.whatsapp.service import webhook
from runtime.whatsapp.service.webhook import Delivery, Inbound, MetaApp, OwnApp, Receipt
from tests.conftest import needs_the_database
from tests.fakes.meta import OUR_NUMBER, SIGNING, a_body, a_text, signed

VAULT = Vault(Fernet.generate_key().decode())
THEIRS = "the secret of an org's own app"


def meta_app() -> MetaApp:
    """The box's Meta app."""
    return MetaApp(app_secret=SIGNING, verify_token="a word", access_token="the box's")


# ── the handshake ──


def test_metas_handshake_is_echoed_back_when_the_word_is_the_right_one() -> None:
    assert webhook.handshake(meta_app(), VAULT, "subscribe", "a word", "1158201444") == "1158201444"


@pytest.mark.parametrize(("mode", "word"), [("subscribe", "another"), ("unsubscribe", "a word"), (None, None)])
def test_a_handshake_with_another_word_echoes_nothing(mode: str | None, word: str | None) -> None:
    with pytest.raises(Forbidden):
        webhook.handshake(meta_app(), VAULT, mode, word, "1158201444")


def test_the_word_the_box_gave_an_org_subscribes_that_orgs_own_app() -> None:
    """An org's own Meta app is given the box's address and a word the box knows again, storing nothing."""
    subscription = webhook.subscription_of(VAULT, "org_ana", "https://box.example")
    assert subscription.callback_url == "https://box.example/v1/whatsapp/webhook"
    assert subscription.field == "messages"
    assert webhook.handshake(None, VAULT, "subscribe", subscription.verify_token, "77") == "77"
    assert webhook.handshake(meta_app(), VAULT, "subscribe", subscription.verify_token, "77") == "77"


@pytest.mark.parametrize("word", ["org_ana.0000", "org_eva.{mark}", ".{mark}", "{mark}"])
def test_a_word_the_box_never_gave_subscribes_nothing(word: str) -> None:
    """Another org's name on a word, a mark made up, a word from another box: none echoes the challenge."""
    mark = webhook.subscription_of(VAULT, "org_ana", "https://box.example").verify_token.rpartition(".")[2]
    with pytest.raises(Forbidden):
        webhook.handshake(None, VAULT, "subscribe", word.format(mark=mark), "77")
    other_box = webhook.subscription_of(Vault(Fernet.generate_key().decode()), "org_ana", "https://box.example")
    with pytest.raises(Forbidden):
        webhook.handshake(meta_app(), VAULT, "subscribe", other_box.verify_token, "77")


# ── the signature ──


def test_the_body_meta_signed_is_taken() -> None:
    body = a_body(a_text("hola"))
    assert webhook.is_signed(SIGNING, body, signed(body))


def test_no_header_at_all_is_refused() -> None:
    assert not webhook.is_signed(SIGNING, b"{}", None)


def test_a_header_without_the_prefix_is_refused() -> None:
    body = a_body(a_text("hola"))
    assert not webhook.is_signed(SIGNING, body, signed(body).removeprefix("sha256="))


def test_a_body_signed_with_another_secret_is_refused() -> None:
    body = a_body(a_text("hola"))
    assert not webhook.is_signed(SIGNING, body, signed(body, "another secret"))


def test_a_body_changed_after_it_was_signed_is_refused() -> None:
    body = a_body(a_text("hola"))
    assert not webhook.is_signed(SIGNING, body.replace(b"hola", b"chau"), signed(body))


# ── the messages in a body ──


def test_one_text_arrives_with_the_door_the_person_and_what_they_wrote() -> None:
    (message,) = webhook.messages_in(a_body(a_text("quiero un turno")))
    assert message == Inbound(
        number=OUR_NUMBER,
        phone_number_id="1055",
        wa_id="59899000001",
        name="Ana",
        message_id="wamid.1",
        kind="text",
        text="quiero un turno",
    )
    assert message.caller == "+59899000001"


def test_two_messages_in_one_body_arrive_in_the_order_meta_sent_them() -> None:
    body = a_body(a_text("uno", message="wamid.1"), a_text("dos", message="wamid.2"))
    assert [item.text for item in webhook.messages_in(body)] == ["uno", "dos"]


def test_a_delivery_receipt_carries_no_message_and_yields_none() -> None:
    value = {
        "metadata": {"display_phone_number": "598", "phone_number_id": "1"},
        "statuses": [{"id": "wamid.1", "status": "read"}],
    }
    body = json.dumps({"entry": [{"changes": [{"value": value}]}]}).encode()
    assert webhook.messages_in(body) == []


def test_an_image_arrives_as_its_own_kind_with_no_text() -> None:
    (image,) = webhook.messages_in(
        a_body({"from": "59899000001", "id": "wamid.9", "type": "image", "image": {"id": "m"}})
    )
    assert (image.kind, image.text) == ("image", None)


def test_a_sender_no_contact_row_names_is_still_a_message_and_has_no_name() -> None:
    (message,) = webhook.messages_in(a_body(a_text("hola"), contacts=[]))
    assert message.name is None


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b'{"entry": "nope"}'])
def test_a_body_that_is_not_a_message_envelope_at_all_yields_none(body: bytes) -> None:
    assert webhook.messages_in(body) == []


def test_a_button_or_a_list_row_tapped_arrives_as_the_words_on_it() -> None:
    """A reply button, a row of a list and a template's quick reply are read as what they say."""
    who = {"from": "59899000001"}
    tapped: list[dict[str, object]] = [
        {**who, "id": "wamid.1", "type": "interactive", "interactive": {"button_reply": {"title": "Sí"}}},
        {**who, "id": "wamid.2", "type": "interactive", "interactive": {"list_reply": {"title": "Lunes"}}},
        {**who, "id": "wamid.3", "type": "button", "button": {"text": "Confirmar", "payload": "ok"}},
    ]
    assert [(item.kind, item.text) for item in webhook.messages_in(a_body(*tapped))] == [
        ("interactive", "Sí"),
        ("interactive", "Lunes"),
        ("button", "Confirmar"),
    ]


def test_a_voice_note_arrives_with_where_its_audio_is_and_no_text() -> None:
    (note,) = webhook.messages_in(
        a_body({"from": "59899000001", "id": "wamid.4", "type": "audio", "audio": {"id": "media.7", "voice": True}})
    )
    assert (note.kind, note.text, note.media_id) == ("audio", None, "media.7")


# ── whose app signed a body ──


def own_app(org: str = "org_ana", number: str = "1055", secret: str = THEIRS) -> OwnApp:
    """An org's own Meta app, as the number it brought names it."""
    return OwnApp(org=org, phone_number_id=number, app_secret=secret)


def test_a_body_the_boxs_app_signed_vouches_for_every_number() -> None:
    body = a_body(a_text("hola"))
    (message,) = webhook.read_signed(meta_app(), [own_app()], body, signed(body)).messages
    assert message.signed_for is None
    assert message.may_reach("any org", None)


def test_a_body_an_orgs_own_app_signed_vouches_for_that_orgs_number_alone() -> None:
    """Signed with the secret an org brought with its number: its messages are taken, for that org and that number."""
    body = a_body(a_text("hola"))
    (message,) = webhook.read_signed(meta_app(), [own_app()], body, signed(body, THEIRS)).messages
    assert message.signed_for == frozenset({"org_ana"})
    assert message.may_reach("org_ana", "1055")
    assert not message.may_reach("org_eva", "1055")
    assert not message.may_reach("org_ana", "2077")
    assert not message.may_reach("org_ana", None)


def test_two_orgs_that_brought_one_number_with_one_app_are_both_vouched_for() -> None:
    body = a_body(a_text("hola"))
    (message,) = webhook.read_signed(
        None, [own_app("org_ana"), own_app("org_eva")], body, signed(body, THEIRS)
    ).messages
    assert message.signed_for == frozenset({"org_ana", "org_eva"})


def test_an_app_signs_for_its_own_numbers_and_never_for_one_it_only_names() -> None:
    """An org signs a body that names another org's number: the secret is not that number's, and nothing is read."""
    forged = a_body(a_text("hola"), phone_number_id="2077")
    theirs = own_app("org_eva", "2077", "another secret")
    with pytest.raises(Forbidden, match="no Meta app this box knows"):
        webhook.read_signed(meta_app(), [theirs], forged, signed(forged, THEIRS))
    # Named beside a number that is the signer's own, it is still not the signer's to vouch for.
    assert webhook.read_signed(meta_app(), [own_app(), theirs], forged, signed(forged, THEIRS)) == Delivery([], [])


@pytest.mark.parametrize("box", [None, meta_app()])
def test_a_body_nobody_signed_is_refused_with_or_without_an_app_of_the_boxs(box: MetaApp | None) -> None:
    body = a_body(a_text("hola"))
    with pytest.raises(Forbidden):
        webhook.read_signed(box, [own_app()], body, signed(body, "a stranger's"))
    with pytest.raises(Forbidden):
        webhook.read_signed(box, [], body, None)


def a_receipt_body(*statuses: dict[str, object], phone_number_id: str = "1055") -> bytes:
    """Meta's envelope around receipts of messages sent from the box's number."""
    value = {
        "metadata": {"display_phone_number": OUR_NUMBER.lstrip("+"), "phone_number_id": phone_number_id},
        "statuses": list(statuses),
    }
    return json.dumps({"entry": [{"changes": [{"field": "messages", "value": value}]}]}).encode()


def test_a_receipt_says_which_message_of_the_agents_stands_where_for_which_contact() -> None:
    """Sent, delivered, read, each names the message and the contact; a failed one carries Meta's words."""
    failed = {"code": 131047, "title": "Re-engagement message", "message": "More than 24 hours have passed"}
    body = a_receipt_body(
        {"id": "wamid.out.1", "status": "delivered", "recipient_id": "59899000001", "timestamp": "1"},
        {"id": "wamid.out.2", "status": "failed", "recipient_id": "59899000001", "errors": [failed]},
        {"id": "", "status": "read", "recipient_id": "59899000001"},
    )
    assert webhook.messages_in(body) == []
    assert webhook.receipts_in(body) == [
        Receipt(OUR_NUMBER, "1055", "59899000001", "wamid.out.1", "delivered"),
        Receipt(OUR_NUMBER, "1055", "59899000001", "wamid.out.2", "failed", "More than 24 hours have passed"),
    ]
    assert webhook.receipts_in(a_body(a_text("hola"))) == []


def test_a_receipt_an_orgs_app_signed_is_taken_for_that_orgs_number_alone() -> None:
    """Meta sends an app every receipt: refused, it would disable the org's webhook; taken, it vouches as a message."""
    body = a_receipt_body({"id": "wamid.out.1", "status": "read", "recipient_id": "59899000001"})
    delivery = webhook.read_signed(None, [own_app()], body, signed(body, THEIRS))
    (receipt,) = delivery.receipts
    assert delivery.messages == []
    assert (receipt.status, receipt.caller, receipt.signed_for) == ("read", "+59899000001", frozenset({"org_ana"}))
    assert receipt.may_reach("org_ana", "1055")
    assert not receipt.may_reach("org_eva", "1055")
    (by_the_box,) = webhook.read_signed(meta_app(), [], body, signed(body)).receipts
    assert by_the_box.signed_for is None


class Kept:
    """The threads, as the webhook is handed them: what was received and what was noted."""

    def __init__(self) -> None:
        """Nothing yet."""
        self.received: list[str] = []
        self.noted: list[str] = []

    async def receive(self, inbound: Inbound) -> bool:
        """Keep the message's id; one named `busy` is being read by another delivery."""
        self.received.append(inbound.message_id)
        return inbound.message_id != "busy"

    async def note(self, receipt: Receipt) -> None:
        """Keep the receipt's status; one for the message `broken` cannot be said."""
        if receipt.message_id == "broken":
            raise RuntimeError("the conversation's log did not take it")
        self.noted.append(receipt.status)


async def test_every_message_is_received_and_every_receipt_noted_and_the_messages_are_counted() -> None:
    """A receipt that cannot be said is a line in the log: the body is answered, and the next receipt is said."""
    kept = Kept()
    messages = webhook.messages_in(a_body(a_text("uno", message="wamid.1"), a_text("dos", message="wamid.2")))
    receipts = [
        Receipt(OUR_NUMBER, "1055", "59899000001", "broken", "sent"),
        Receipt(OUR_NUMBER, "1055", "59899000001", "wamid.out.1", "delivered"),
    ]
    assert await webhook.receive_all(kept, Delivery(messages, receipts)) == 2
    assert (kept.received, kept.noted) == (["wamid.1", "wamid.2"], ["delivered"])
    with pytest.raises(ServiceUnavailable, match="another delivery"):
        await webhook.receive_all(kept, Delivery(webhook.messages_in(a_body(a_text("x", message="busy"))), []))


def test_the_numbers_a_body_names_are_read_before_anybody_vouched_for_it() -> None:
    assert webhook.numbers_named_in(a_body(a_text("hola"))) == {"1055"}
    assert webhook.numbers_named_in(b"not json") == set()
    many = [{"value": {"metadata": {"phone_number_id": str(number)}}} for number in range(webhook.FEW_NUMBERS + 1)]
    assert webhook.numbers_named_in(json.dumps({"entry": [{"changes": many}]}).encode()) == set()


@needs_the_database
async def test_a_box_with_no_meta_app_has_its_door_closed(sessions: async_sessionmaker[AsyncSession]) -> None:
    """With no Meta app among the box's credentials, the box answers no number of its own, saying which."""
    async with sessions() as session:
        assert await webhook.find_box_meta_app(session, VAULT) is None
        with pytest.raises(ServiceUnavailable, match="credentials/whatsapp"):
            await webhook.box_meta_app(session, VAULT)


# ── a Page's messages: Messenger, and the Instagram account linked to it ──

PAGE = "1472943555898656"
INSTAGRAM = "17841400000000001"


def a_page_body(*events: dict[str, object], kind: str = "page", account: str = PAGE) -> bytes:
    """A Messenger Platform body as Meta writes it: one account's events, under `entry[].messaging[]`."""
    return json.dumps({"object": kind, "entry": [{"id": account, "time": 1, "messaging": list(events)}]}).encode()


def an_event(**said: object) -> dict[str, object]:
    """One event of a contact's, sent to the account."""
    return {"sender": {"id": "7001"}, "recipient": {"id": PAGE}, "timestamp": 1764200000000, **said}


def a_page_app(account: str = PAGE, secret: str = THEIRS) -> OwnApp:
    """An org's own Meta app, as the Page it brought names it, or the Instagram account linked to that Page."""
    return OwnApp(org="org_ana", phone_number_id=account, app_secret=secret, answers_from=PAGE)


def test_a_message_to_a_page_arrives_on_messenger_from_metas_id_of_the_contact() -> None:
    body = a_page_body(an_event(message={"mid": "m_1", "text": "hola"}))
    (message,) = webhook.read_signed(None, [a_page_app()], body, signed(body, THEIRS)).messages
    assert (message.channel, message.number, message.phone_number_id, message.wa_id) == (
        "messenger",
        PAGE,
        PAGE,
        "7001",
    )
    assert (message.kind, message.text, message.message_id, message.caller) == ("text", "hola", "m_1", "messenger:7001")
    assert message.may_reach("org_ana", PAGE)


def test_a_message_to_the_instagram_account_is_answered_from_the_page_it_is_linked_to() -> None:
    body = a_page_body(an_event(message={"mid": "ig_1", "text": "hola"}), kind="instagram", account=INSTAGRAM)
    (message,) = webhook.read_signed(None, [a_page_app(INSTAGRAM)], body, signed(body, THEIRS)).messages
    assert (message.channel, message.number, message.phone_number_id, message.caller) == (
        "instagram",
        INSTAGRAM,
        PAGE,
        "instagram:7001",
    )
    assert message.may_reach("org_ana", PAGE)


def test_our_own_sends_come_back_as_echoes_and_are_never_read_as_the_contacts() -> None:
    body = a_page_body(
        an_event(message={"mid": "m_2", "text": "¡Hola!", "is_echo": True}), kind="instagram", account=INSTAGRAM
    )
    assert webhook.messaging_in(body, {INSTAGRAM: PAGE}).messages == []


def test_a_button_tapped_arrives_as_its_title_and_a_voice_note_as_its_link() -> None:
    note = {"mid": "m_3", "attachments": [{"type": "audio", "payload": {"url": "https://cdn.fbsbx.example/n.mp4"}}]}
    body = a_page_body(
        an_event(postback={"mid": "m_4", "title": "Ver casas", "payload": "CASAS"}), an_event(message=note)
    )
    tapped, heard = webhook.messaging_in(body, {PAGE: PAGE}).messages
    assert (tapped.kind, tapped.text) == ("button", "Ver casas")
    assert (heard.kind, heard.text, heard.media_id) == ("audio", None, "https://cdn.fbsbx.example/n.mp4")


def test_a_delivery_and_a_read_become_receipts_of_the_agents_messages() -> None:
    body = a_page_body(
        an_event(delivery={"mids": ["m_5", "m_6"]}), an_event(read={"mid": "m_6"}), kind="instagram", account=INSTAGRAM
    )
    found = webhook.messaging_in(body, {INSTAGRAM: PAGE})
    assert found.messages == []
    assert [(one.message_id, one.status, one.channel, one.phone_number_id) for one in found.receipts] == [
        ("m_5", "delivered", "instagram", PAGE),
        ("m_6", "delivered", "instagram", PAGE),
        ("m_6", "read", "instagram", PAGE),
    ]


def test_a_page_body_no_org_s_app_signed_is_refused_and_the_box_s_own_app_signs_none() -> None:
    body = a_page_body(an_event(message={"mid": "m_7", "text": "hola"}))
    with pytest.raises(Forbidden, match="carriers add messenger"):
        webhook.read_signed(meta_app(), [a_page_app()], body, signed(body))
    with pytest.raises(Forbidden):
        webhook.read_signed(None, [a_page_app(secret="another app's")], body, signed(body, THEIRS))


def test_the_accounts_a_page_body_names_are_read_and_a_whatsapp_body_names_none() -> None:
    assert webhook.accounts_named_in(a_page_body(an_event(message={"mid": "m_8", "text": "hola"}))) == {PAGE}
    assert webhook.accounts_named_in(a_body(a_text("hola"))) == set()
    assert webhook.numbers_named_in(a_page_body(an_event(message={"mid": "m_9", "text": "hola"}))) == set()
