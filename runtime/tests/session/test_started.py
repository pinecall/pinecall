"""The call.started entry: who is on the line when the call opens, and what it was opened with."""

from dataclasses import replace

from pinecall_runtime.calls.context import Contact
from pinecall_runtime.enums import Channel, Medium
from pinecall_runtime.session.started import started
from tests.session.conftest import THE_CALLER, context_of

AT = 1_790_000_000.0


def test_a_call_opened_with_a_contact_names_it_as_the_caller_and_leaves_the_visitor_id_as_from() -> None:
    """`chat --as +1415…`: the hook reads the contact, the line still says which visitor it came through."""
    context = context_of("call_1", Channel.web, contact=Contact(id="+14155550198"))
    line = started(context, AT, None, medium=Medium.text)
    assert line.caller is not None and line.caller.id == "+14155550198"
    assert line.dump()["caller"] == {"id": "+14155550198"}
    assert line.from_ == THE_CALLER


def test_a_contact_carries_every_field_it_was_opened_with_and_none_it_was_not() -> None:
    """A WhatsApp conversation opens with the number and the name the platform gave: both are on the entry."""
    context = context_of("call_1", Channel.whatsapp, contact=Contact(phone=THE_CALLER, name="Marta"))
    assert started(context, AT, None, medium=Medium.text).dump()["caller"] == {"phone": THE_CALLER, "name": "Marta"}


def test_a_call_opened_with_nobody_named_has_no_caller_yet() -> None:
    """A web visitor nobody named, and a contact with nothing in it, are the same: null, as the wire says."""
    assert started(context_of("call_1", Channel.web), AT, None, medium=Medium.text).dump()["caller"] is None
    empty = context_of("call_1", Channel.web, contact=Contact())
    assert started(empty, AT, None, medium=Medium.text).dump()["caller"] is None


def test_what_a_call_was_opened_with_is_on_the_entry_for_the_app_to_read() -> None:
    """The token's sealed `metadata` reaches the app as `call.started.metadata`, as sent."""
    context = replace(context_of("call_1", Channel.web), metadata={"plan": "gold", "seats": 3})
    assert started(context, AT, None, medium=Medium.text).dump()["metadata"] == {"plan": "gold", "seats": 3}


def test_a_call_opened_with_no_metadata_says_none() -> None:
    """Nothing sealed into the call: the entry has no `metadata` key at all."""
    assert "metadata" not in started(context_of("call_1", Channel.web), AT, None, medium=Medium.text).dump()
