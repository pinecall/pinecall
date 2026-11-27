"""Tests for a Page's bodies on the webhook: Messenger's and its Instagram's messages, receipts, and who signed them."""

import json

import pytest

from runtime.exceptions import Forbidden
from runtime.whatsapp.service import messaging, webhook
from runtime.whatsapp.service.webhook import OwnApp
from tests.fakes.meta import a_body, a_text, signed

THEIRS = "the secret of an org's own app"

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
    (message,) = messaging.read_signed([a_page_app()], body, signed(body, THEIRS)).messages
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
    (message,) = messaging.read_signed([a_page_app(INSTAGRAM)], body, signed(body, THEIRS)).messages
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
    assert messaging.messaging_in(body, {INSTAGRAM: PAGE}).messages == []


def test_a_button_tapped_arrives_as_its_title_and_a_voice_note_as_its_link() -> None:
    note = {"mid": "m_3", "attachments": [{"type": "audio", "payload": {"url": "https://cdn.fbsbx.example/n.mp4"}}]}
    body = a_page_body(
        an_event(postback={"mid": "m_4", "title": "Ver casas", "payload": "CASAS"}), an_event(message=note)
    )
    tapped, heard = messaging.messaging_in(body, {PAGE: PAGE}).messages
    assert (tapped.kind, tapped.text) == ("button", "Ver casas")
    assert (heard.kind, heard.text, heard.media_id) == ("audio", None, "https://cdn.fbsbx.example/n.mp4")


def test_a_delivery_and_a_read_become_receipts_of_the_agents_messages() -> None:
    body = a_page_body(
        an_event(delivery={"mids": ["m_5", "m_6"]}), an_event(read={"mid": "m_6"}), kind="instagram", account=INSTAGRAM
    )
    found = messaging.messaging_in(body, {INSTAGRAM: PAGE})
    assert found.messages == []
    assert [(one.message_id, one.status, one.channel, one.phone_number_id) for one in found.receipts] == [
        ("m_5", "delivered", "instagram", PAGE),
        ("m_6", "delivered", "instagram", PAGE),
        ("m_6", "read", "instagram", PAGE),
    ]


def test_a_page_body_no_orgs_app_signed_is_refused_and_the_boxs_own_secret_signs_none() -> None:
    body = a_page_body(an_event(message={"mid": "m_7", "text": "hola"}))
    with pytest.raises(Forbidden, match="carriers add messenger"):
        messaging.read_signed([a_page_app()], body, signed(body))
    with pytest.raises(Forbidden):
        messaging.read_signed([a_page_app(secret="another app's")], body, signed(body, THEIRS))


def test_the_accounts_a_page_body_names_are_read_and_a_whatsapp_body_names_none() -> None:
    assert messaging.accounts_named_in(a_page_body(an_event(message={"mid": "m_8", "text": "hola"}))) == {PAGE}
    assert messaging.accounts_named_in(a_body(a_text("hola"))) == set()
    assert messaging.is_a_page_body(a_page_body()) and not messaging.is_a_page_body(a_body(a_text("hola")))
    assert webhook.numbers_named_in(a_page_body(an_event(message={"mid": "m_9", "text": "hola"}))) == set()
