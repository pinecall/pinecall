"""Tests for Meta's Graph: a reply or a template sent, a long one cut, a message read, a note fetched, a number."""

import httpx
import pytest

from runtime.exceptions import UpstreamError
from runtime.whatsapp.service import graph, webhook
from tests.fakes.meta import Graph, a_body, a_text, outside
from tests.fakes.twilio import Twilio
from tests.fakes.webhooks import Receiver

# ── a reply ──


async def test_a_reply_goes_from_the_number_written_to_with_no_preview_on_the_token() -> None:
    meta = Graph()
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        (message,) = webhook.messages_in(a_body(a_text("hola")))
        await graph.send_text(http, "a token", message, "¡Hola Ana!")
    (sent,) = meta.sent
    assert sent["from"] == "1055"
    assert (sent["to"], sent["text"]) == (
        "59899000001",
        {"body": "¡Hola Ana!", "preview_url": False},
    )
    assert meta.tokens == ["Bearer a token"]


async def test_a_reply_meta_refuses_is_refused_in_metas_own_words() -> None:
    meta = Graph(refusal=(400, "Message failed to send because more than 24 hours have passed"))
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        (message,) = webhook.messages_in(a_body(a_text("hola")))
        with pytest.raises(UpstreamError, match="more than 24 hours"):
            await graph.send_text(http, "a token", message, "hola")


# ── a template ──


async def test_a_template_goes_from_the_number_filled_in_order_and_meta_names_the_message() -> None:
    meta = Graph()
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        filled = graph.Template("consulta_por_propiedad", "es_AR", ("Micaela", "la casa de Olazaval al 400"))
        assert await graph.send_template(http, "a token", "1055", "+5491155550134", filled) == "wamid.1"
        assert (
            await graph.send_template(http, "a token", "1055", "+5491155550134", graph.Template("hola", "es"))
            == "wamid.2"
        )
    with_variables, bare = meta.sent
    assert (with_variables["from"], with_variables["to"], with_variables["type"]) == (
        "1055",
        "5491155550134",
        "template",
    )
    assert with_variables["template"] == {
        "name": "consulta_por_propiedad",
        "language": {"code": "es_AR"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Micaela"},
                    {"type": "text", "text": "la casa de Olazaval al 400"},
                ],
            }
        ],
    }
    assert bare["template"] == {"name": "hola", "language": {"code": "es"}, "components": []}


async def test_a_template_meta_refuses_is_refused_in_metas_own_words() -> None:
    meta = Graph(refusal=(400, "Template name does not exist in the translation"))
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        with pytest.raises(UpstreamError, match="does not exist in the translation"):
            await graph.send_template(http, "a token", "1055", "+5491155550134", graph.Template("nada", "es_AR"))


# ── the number an account is ──


async def test_the_number_an_account_answers_at_is_asked_of_meta_in_e164() -> None:
    meta = Graph(number="+1 555-010-0000", name="Clinica Norte")
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        assert await graph.number_of(http, "a token", "1055") == graph.MetaNumber("+15550100000", "Clinica Norte")
        meta.refusal = (401, "Error validating access token: Session has expired")
        with pytest.raises(UpstreamError, match="expired"):
            await graph.number_of(http, "a token", "1055")


# ── a long reply ──


async def test_a_long_reply_goes_out_as_several_messages_in_order() -> None:
    meta = Graph()
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        (message,) = webhook.messages_in(a_body(a_text("hola")))
        await graph.send_text(http, "a token", message, "uno " * 800 + "\n\n" + "dos " * 800)
    assert len(meta.sent) == 2
    assert (str(meta.sent[0]["text"]).count("uno"), str(meta.sent[1]["text"]).count("dos")) == (800, 800)


# ── read, and typing ──


async def test_a_message_is_marked_read_and_typing_is_shown_only_when_asked() -> None:
    meta = Graph()
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        (message,) = webhook.messages_in(a_body(a_text("hola")))
        await graph.mark_read(http, "a token", message, typing=True)
        await graph.mark_read(http, "a token", message, typing=False)
    assert meta.read == [("wamid.1", True), ("wamid.1", False)]
    assert meta.sent == []


# ── a voice note ──


async def test_a_voice_notes_audio_is_fetched_where_meta_says_it_is_on_the_numbers_token() -> None:
    meta = Graph(media={"media.7": (b"OggS-some-audio", "audio/ogg; codecs=opus")})
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        media = await graph.read_media(http, "a token", "media.7")
    assert (media.data, media.mime_type) == (b"OggS-some-audio", "audio/ogg; codecs=opus")


async def test_a_voice_note_longer_than_is_heard_is_refused() -> None:
    meta = Graph(media={"media.8": (b"x" * (graph.LONGEST_MEDIA + 1), "audio/ogg")})
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        with pytest.raises(UpstreamError, match="longer than is heard"):
            await graph.read_media(http, "a token", "media.8")
