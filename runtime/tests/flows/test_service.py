"""An app's events and its flows on the served gateway: owed until heard, journaled in order, woken by the clock."""

from datetime import timedelta
from typing import Any

from pinecall_runtime.flows import service
from pinecall_runtime.kit.time import now
from tests.conftest import Gateway, Tenant, needs_the_services

APP = "/v1/apps/brightside"


async def _post(gateway: Gateway, tenant: Tenant, path: str, body: dict[str, Any] | None = None) -> Any:
    answered = await gateway.http.post(f"{APP}{path}", json=body or {}, headers=tenant.person)
    assert answered.status_code < 300, answered.text
    return answered.json() if answered.content else None


async def _work(gateway: Gateway, tenant: Tenant) -> dict[str, Any]:
    owed: dict[str, Any] = await _post(gateway, tenant, "/work", {"wait_s": 0})
    return owed


async def _started(gateway: Gateway, tenant: Tenant, key: str = "evt-1") -> str:
    run = await _post(gateway, tenant, "/runs", {"flow": "remindVisit", "key": key, "input": {"visit": "v-812"}})
    return str(run["id"])


@needs_the_services
async def test_an_event_is_owed_until_the_app_says_it_heard_it(gateway: Gateway, tenant: Tenant) -> None:
    """Handed to one process at a time, and gone once heard: a process that is down loses nothing."""
    sent = await _post(gateway, tenant, "/events", {"name": "visit.cancelled", "data": {"id": "v-812"}})
    owed = (await _work(gateway, tenant))["events"]
    assert [(event["id"], event["name"], event["data"]) for event in owed] == [
        (sent["id"], "visit.cancelled", {"id": "v-812"})
    ]
    assert (await _work(gateway, tenant))["events"] == []
    await _post(gateway, tenant, f"/events/{sent['id']}/heard")
    refused = await gateway.http.post(f"{APP}/events/{sent['id']}/heard", headers=tenant.person)
    assert refused.status_code == 404, refused.text


@needs_the_services
async def test_a_key_starts_a_flow_once_and_the_run_is_handed_out_with_its_journal(
    gateway: Gateway, tenant: Tenant
) -> None:
    run = await _started(gateway, tenant)
    assert await _started(gateway, tenant) == run
    ready = (await _work(gateway, tenant))["runs"]
    assert [(one["id"], one["flow"], one["input"], one["steps"]) for one in ready] == [
        (run, "remindVisit", {"visit": "v-812"}, [])
    ]


@needs_the_services
async def test_a_run_sleeps_until_its_hour_and_goes_on_from_its_journal(gateway: Gateway, tenant: Tenant) -> None:
    """What a step came to is read back, never run again; the clock is the gateway's."""
    run = await _started(gateway, tenant)
    await _post(gateway, tenant, f"/runs/{run}/steps", {"seq": 1, "kind": "run", "result": {"sent": True}})
    past = (now() - timedelta(seconds=5)).isoformat()
    slept = await _post(gateway, tenant, f"/runs/{run}/steps", {"seq": 2, "kind": "sleep", "asked": {"until": past}})
    assert slept["status"] == "sleeping"
    assert (await _work(gateway, tenant))["runs"] == []
    async with gateway.app.state.handles.sessions.begin() as session:
        assert await service.wake_due(session) >= 1
    [woken] = (await _work(gateway, tenant))["runs"]
    assert [(step["kind"], step["over"], step["result"]) for step in woken["steps"]] == [
        ("run", True, {"sent": True}),
        ("sleep", True, None),
    ]
    ended = await _post(gateway, tenant, f"/runs/{run}/end", {"status": "done"})
    assert ended["status"] == "done"


@needs_the_services
async def test_a_run_waits_for_the_event_that_matches_and_for_no_other(gateway: Gateway, tenant: Tenant) -> None:
    run = await _started(gateway, tenant)
    asked = {"event": "refund.decided", "match": {"id": "r-1"}}
    waiting = await _post(gateway, tenant, f"/runs/{run}/steps", {"seq": 1, "kind": "wait", "asked": asked})
    assert (waiting["status"], waiting["waits_for"]) == ("waiting", "refund.decided")
    await _post(gateway, tenant, "/events", {"name": "refund.decided", "data": {"id": "r-2", "approved": True}})
    assert (await _work(gateway, tenant))["runs"] == []
    await _post(gateway, tenant, "/events", {"name": "refund.decided", "data": {"id": "r-1", "approved": True}})
    [woken] = (await _work(gateway, tenant))["runs"]
    assert woken["steps"][0]["result"] == {"id": "r-1", "approved": True}


@needs_the_services
async def test_a_wait_that_gives_up_comes_to_nothing(gateway: Gateway, tenant: Tenant) -> None:
    run = await _started(gateway, tenant)
    past = (now() - timedelta(seconds=5)).isoformat()
    await _post(
        gateway, tenant, f"/runs/{run}/steps", {"seq": 1, "kind": "wait", "asked": {"event": "x", "until": past}}
    )
    async with gateway.app.state.handles.sessions.begin() as session:
        await service.wake_due(session)
    [woken] = (await _work(gateway, tenant))["runs"]
    assert (woken["steps"][0]["over"], woken["steps"][0]["result"]) == (True, None)


@needs_the_services
async def test_the_journal_is_written_in_order_and_a_step_sent_again_is_the_one_written(
    gateway: Gateway, tenant: Tenant
) -> None:
    """A retry writes nothing twice, and a flow whose code changed under a run is told so."""
    run = await _started(gateway, tenant)
    skipped = await gateway.http.post(f"{APP}/runs/{run}/steps", json={"seq": 2, "kind": "run"}, headers=tenant.person)
    assert skipped.status_code == 409 and "written in order" in skipped.text
    await _post(gateway, tenant, f"/runs/{run}/steps", {"seq": 1, "kind": "run", "result": 1})
    await _post(gateway, tenant, f"/runs/{run}/steps", {"seq": 1, "kind": "run", "result": 2})
    read = (await gateway.http.get(f"{APP}/runs/{run}", headers=tenant.person)).json()
    assert [step["result"] for step in read["steps"]] == [1]
    other = await gateway.http.post(f"{APP}/runs/{run}/steps", json={"seq": 1, "kind": "sleep"}, headers=tenant.person)
    assert other.status_code == 409 and "code changed under a run" in other.text


@needs_the_services
async def test_a_call_nobody_can_place_is_the_steps_answer_and_the_run_goes_on(
    gateway: Gateway, tenant: Tenant
) -> None:
    run = await _started(gateway, tenant)
    asked = {"agent": "reminder", "to": "+14155550142"}
    called = await _post(gateway, tenant, f"/runs/{run}/steps", {"seq": 1, "kind": "call", "asked": asked})
    assert called["status"] == "ready"
    read = (await gateway.http.get(f"{APP}/runs/{run}", headers=tenant.person)).json()
    assert read["steps"][0]["result"]["refused"] == "no_app"


@needs_the_services
async def test_a_cancelled_run_stays_cancelled_and_is_listed_by_its_status(gateway: Gateway, tenant: Tenant) -> None:
    run = await _started(gateway, tenant)
    assert (await _post(gateway, tenant, f"/runs/{run}/cancel"))["status"] == "cancelled"
    assert (await _post(gateway, tenant, f"/runs/{run}/end", {"status": "done"}))["status"] == "cancelled"
    listed = (await gateway.http.get(f"{APP}/runs", params={"status": "cancelled"}, headers=tenant.person)).json()
    assert [one["id"] for one in listed["runs"]] == [run]
