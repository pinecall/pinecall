"""The call as an agent holds it: each verb one command, the ones that wait answered by the log."""

import asyncio

import pytest
from pydantic import ValidationError

from pinecall import CallLine, CallWorld, PinecallError
from pinecall import call as calls
from pinecall._answers import NO_ANSWER, THE_CALL_ENDED
from pinecall.client import Found
from pinecall.wire._names import JsonObject
from pinecall.wire.events import EVENTS
from pinecall.wire.frames import WireModel

LINE = CallLine(id="CA_1", contact="+34600", from_="+34600", channel="phone", today="2026-10-07")


def a_world(
    sent: list[tuple[str, JsonObject]],
    loop: asyncio.AbstractEventLoop | None = None,
    searching: calls.Searching | None = None,
) -> CallWorld:
    def send(type_: str, data: WireModel) -> None:
        sent.append((type_, data.written()))

    return CallWorld(LINE, send, searching, loop)


def event(type_: str, data: JsonObject) -> WireModel:
    return EVENTS[type_].read(data, type_)


async def test_a_transfer_the_far_end_answered_says_so() -> None:
    sent: list[tuple[str, JsonObject]] = []
    world = a_world(sent, asyncio.get_running_loop())
    asked = world.transfer("+34910")
    world.take(event("call.transferred", {"to": "+34910", "mode": "cold", "ok": True}), 1.0)
    transferred = await asked
    assert sent == [("call.transfer", {"to": "+34910"})]
    assert (transferred.ok, transferred.mode) == (True, "cold")


async def test_a_transfer_nobody_answers_says_the_runtime_never_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(calls, "TRANSFERRED_WITHIN_S", 0.05)
    sent: list[tuple[str, JsonObject]] = []
    transferred = await a_world(sent, asyncio.get_running_loop()).transfer("+34910", mode="warm")
    assert sent == [("call.transfer", {"to": "+34910", "mode": "warm"})]
    assert (transferred.ok, transferred.error) == (False, NO_ANSWER)


async def test_attention_waits_for_the_supervisor_who_takes_the_line() -> None:
    sent: list[tuple[str, JsonObject]] = []
    world = a_world(sent, asyncio.get_running_loop())
    asked = world.attention("a refund", wait_s=30)
    world.take(
        event("attention.answered", {"ok": True, "by": {"id": "sup_1", "name": "Lucía"}}), 1.0
    )
    attended = await asked
    assert sent == [("call.attention", {"reason": "a refund", "wait_s": 30.0})]
    assert attended.by is not None
    assert (attended.ok, attended.by.name) == (True, "Lucía")


async def test_a_say_is_answered_by_the_turn_it_asked_for_and_waited_for_from_a_thread() -> None:
    sent: list[tuple[str, JsonObject]] = []
    loop = asyncio.get_running_loop()
    world = a_world(sent, loop)
    on_a_thread = asyncio.ensure_future(
        asyncio.to_thread(lambda: world.say("Un momento.").result(2))
    )
    await asyncio.sleep(0.05)
    turn: JsonObject = {
        "speech_id": "s1",
        "text": "Un momento.",
        "interrupted": False,
        "metrics": {},
    }
    world.take(event("turn.agent", turn), 2.0)
    assert await on_a_thread is True
    assert sent == [("agent.say", {"text": "Un momento."})]
    assert [one.text for one in world.history.turns] == ["Un momento."]


async def test_the_call_ending_answers_every_verb_still_waiting() -> None:
    world = a_world([], asyncio.get_running_loop())
    transfer, said = world.transfer("+34910"), world.say("Adiós.")
    ended: JsonObject = {
        "reason": "caller_hung_up",
        "ended_by": "caller",
        "ended_at": 1.0,
        "duration_s": 1.0,
    }
    world.take(event("call.ended", ended), 1.0)
    assert ((await transfer).error, await said) == (THE_CALL_ENDED, False)


def test_hold_unhold_dtmf_and_hangup_are_one_command_each() -> None:
    sent: list[tuple[str, JsonObject]] = []
    world = a_world(sent)
    world.hold()
    world.unhold()
    world.dtmf("12#")
    world.hangup()
    assert sent == [
        ("call.hold", {}),
        ("call.unhold", {}),
        ("call.dtmf", {"digits": "12#"}),
        ("call.hangup", {}),
    ]


def test_a_claim_is_claimed_only_when_the_log_says_it_took_and_a_bad_code_never_leaves() -> None:
    sent: list[tuple[str, JsonObject]] = []
    world = a_world(sent)
    world.claim("4821")
    assert world.claimed is None
    world.take(event("call.claimed", {"code": "4821", "via": "agent"}), 1.0)
    assert world.claimed == "4821"
    assert world.line().claimed == "4821"
    with pytest.raises(ValidationError):
        world.claim("48")
    assert len(sent) == 1


def test_a_callback_says_when_under_the_wires_own_word_and_an_opt_out_its_note() -> None:
    sent: list[tuple[str, JsonObject]] = []
    world = a_world(sent)
    world.callback("+34600", when="2026-10-08T10:00", note="after ten")
    world.opt_out("pidió no volver a recibir llamadas")
    world.opt_out()
    assert sent == [
        ("call.callback", {"number": "+34600", "when": "2026-10-08T10:00", "note": "after ten"}),
        ("call.opt_out", {"note": "pidió no volver a recibir llamadas"}),
        ("call.opt_out", {}),
    ]


def test_the_room_fills_as_people_join_and_a_seat_has_its_two_verbs() -> None:
    sent: list[tuple[str, JsonObject]] = []
    world = a_world(sent)
    joined: JsonObject = {"identity": "sip_ana", "kind": "caller", "name": "Ana", "attributes": {}}
    world.take(event("participant.joined", joined), 1.0)
    world.take(event("participant.speaking", {"identity": "sip_ana", "speaking": True}), 2.0)
    assert world.room.caller is not None
    assert (world.room.caller.name, world.room.caller.speaking) == ("Ana", True)
    world.participant("sip_ana").mute()
    world.invite("+34910")
    world.take(event("participant.left", {"identity": "sip_ana", "reason": "hung_up"}), 3.0)
    assert world.room.participants == []
    assert sent == [
        ("participant.mute", {"identity": "sip_ana"}),
        ("room.invite", {"to": "+34910", "kind": "sip"}),
    ]


def test_a_search_with_no_gateway_says_so() -> None:
    with pytest.raises(PinecallError, match="no gateway is serving it"):
        a_world([]).search("horario")


async def test_a_search_goes_through_the_gateway_for_this_call() -> None:
    asked: list[tuple[str, int | None]] = []

    async def searching(query: str, k: int | None) -> list[Found]:
        asked.append((query, k))
        return [Found("horario.md", "Horario", "de 9 a 18")]

    found = await a_world([], asyncio.get_running_loop(), searching).search("horario", k=2)
    assert asked == [("horario", 2)]
    assert [one.text for one in found] == ["de 9 a 18"]


def test_the_medium_is_the_one_the_channel_implies_when_the_line_does_not_say() -> None:
    assert CallWorld(CallLine(id="WA_1", channel="whatsapp")).medium == "text"
    assert CallWorld(LINE).line() == calls.Line("phone", "voice", None)
