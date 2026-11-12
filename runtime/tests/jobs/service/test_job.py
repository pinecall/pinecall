"""One job, one call: the opening a dialled call brings, and a call no session could be built for, ended at once."""

from runtime.agents.declaration import Declaration, Greeting
from runtime.calls.log.store import Store
from runtime.exceptions import ValidationError
from runtime.jobs.service.client import GatewayClient
from runtime.jobs.service.job import NOT_BUILT, SESSION_FAILED, fail_call, open_as_dialled
from runtime.wire.dispatch import Dispatch
from tests.conftest import Tenant, needs_the_services
from tests.jobs.factories import opened


def test_a_dialled_call_opens_on_its_own_words_or_on_what_it_is_for_and_any_other_on_the_agents() -> None:
    desk = Declaration(slug="desk", greeting=Greeting(say="Brightside Dental."))
    assert open_as_dialled(desk, Dispatch(greeting="Hi Ana, it is Brightside.")).greeting == Greeting(
        say="Hi Ana, it is Brightside."
    )
    assert open_as_dialled(desk, Dispatch(instruction="Remind her of her visit.")).greeting == Greeting(
        reply="Remind her of her visit."
    )
    both = Dispatch(greeting="Hi Ana.", instruction="Remind her of her visit.")
    assert open_as_dialled(desk, both).greeting == Greeting(say="Hi Ana.")
    assert open_as_dialled(desk, Dispatch()) is desk


# A worker whose session could not be built left the call ringing for the reaper's ten minutes, sealed
# `drained` with nothing of why (2026-11-05, a Soniox model the plugin refused as an argument).
@needs_the_services
async def test_a_session_the_worker_cannot_build_ends_the_call_at_once_with_the_refusal_on_its_log(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    link = await opened(fleet, tenant, agent)
    refused = ValidationError("soniox refused its STT: STT.__init__() got an unexpected keyword argument 'model'")
    await fail_call(link, refused)
    await link.aclose()
    entries = await store.whole_of(link.call)
    failed = next(entry for entry in entries if entry.type == "error")
    ended = next(entry for entry in entries if entry.type == "call.ended")
    summary = next(entry for entry in entries if entry.type == "call.summary")
    assert (failed.data["code"], failed.data["recoverable"], failed.data["message"]) == (
        SESSION_FAILED,
        False,
        str(refused),
    )
    assert failed.seq < ended.seq and ended.data["reason"] == "error"
    assert NOT_BUILT.format(why=refused) in str(summary.data)
    assert await store.is_sealed(link.call)
