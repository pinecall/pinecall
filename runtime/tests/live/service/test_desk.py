"""A supervise verb as the gateway sends it to a live call."""

from runtime.live.service.desk import as_sent
from runtime.wire.commands import SayVerb, SupervisorVerb
from runtime.wire.parts import Supervisor


def test_a_verb_the_gateway_writes_itself_is_sent_with_its_name() -> None:
    """A `say` made with its text alone is read as a `say` by the call it is sent to."""
    sent = as_sent(Supervisor(id="m_1", name="Ana"), SayVerb(text="Un momento, por favor."))
    assert sent["verb"] == {"verb": "say", "text": "Un momento, por favor."}
    read = SupervisorVerb.model_validate(sent)
    assert isinstance(read.verb, SayVerb) and read.by.id == "m_1"
