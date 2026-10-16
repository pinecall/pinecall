"""The room and the turns: who joined, who is speaking, who left, and what was said."""

from pinecall._room import History, Participant, Room, Turn
from pinecall.wire.frames import WireModel


def test_a_room_keeps_people_in_the_order_they_joined_and_knows_its_caller() -> None:
    room = Room(lambda type_, data: None)
    room.joined(Participant("agent", "agent", None, 1.0))
    room.joined(Participant("sip_ana", "caller", "Ana", 2.0))
    assert [one.identity for one in room.participants] == ["agent", "sip_ana"]
    assert room.caller is not None
    assert room.caller.identity == "sip_ana"
    assert room.has("agent")
    assert not room.has("supervisor")


def test_someone_speaking_who_is_not_in_the_room_changes_nothing() -> None:
    room = Room(lambda type_, data: None)
    room.speaking("nobody", speaking=True)
    assert room.get("nobody") is None


def test_an_invite_is_one_command() -> None:
    sent: list[tuple[str, WireModel]] = []
    Room(lambda type_, data: sent.append((type_, data))).invite("sup_1", "participant")
    assert [(type_, data.written()) for type_, data in sent] == [
        ("room.invite", {"to": "sup_1", "kind": "participant"})
    ]


def test_the_history_is_the_finished_turns_and_its_last_one() -> None:
    history = History()
    assert history.last is None
    history.took(Turn("user", "Hola.", "s1", interrupted=False, at=1.0))
    history.took(Turn("agent", "Buenos días.", "s1", interrupted=False, at=2.0))
    assert history.last is not None
    assert history.last.text == "Buenos días."
