"""A suite through the gateway: answered as it starts, listed while it plays, each golden a cell."""

import asyncio
import secrets
import time
from collections.abc import Mapping

import pytest

from pinecall_runtime.kit.text import JsonObject, a_list, a_mapping
from tests.conftest import Gateway, Tenant, holding, needs_the_services

# The scripted model answers the caller's own words back, so a reply step on them holds.
A_GOLDEN: JsonObject = {
    "name": "saluda",
    "turns": [{"say": "quiero un turno", "then": [{"reply": {"says_any": ["quiero un turno"]}}]}],
    "expect": {},
}
# Its facts are answered to recall, which an agent that keeps no memory has not.
A_REMEMBERING_GOLDEN: JsonObject = {
    "name": "recuerda",
    "memory": ["prefiere la mañana"],
    "turns": [{"say": "hola", "then": []}],
    "expect": {},
}
A_RUN_ENDS_WITHIN_S = 15.0


@pytest.fixture
def agent() -> str:
    """A slug of this test alone: a slug is one org's, and tests of other orgs run beside it."""
    return f"agent-{secrets.token_hex(4)}"


async def finished_run(gateway: Gateway, tenant: Tenant, run: str) -> JsonObject:
    """The run's row once it is no longer running, read as a terminal following it reads it."""
    deadline = time.monotonic() + A_RUN_ENDS_WITHIN_S
    while True:
        shown = await gateway.http.get(f"/v1/evals/runs/{run}", headers=tenant.server)
        assert shown.status_code == 200, shown.text
        row: JsonObject = shown.json()
        if row["status"] != "running":
            return row
        assert time.monotonic() < deadline, f"run {run} never ended: {row}"
        await asyncio.sleep(0.05)


def cells_of(run: JsonObject) -> dict[str, list[Mapping[str, object]]]:
    """Each golden's scores, by its name."""
    matrix = run["matrix"]
    assert a_mapping(matrix) and a_list(matrix["runs"])
    cells = [cell for cell in matrix["runs"] if a_mapping(cell)]
    return {str(cell["golden"]): [score for score in as_list(cell["scores"]) if a_mapping(score)] for cell in cells}


def goldens_opened(run: JsonObject) -> list[str]:
    """The goldens the run opened a call for, in order."""
    return [str(opened["golden"]) for opened in as_list(run["calls"]) if a_mapping(opened)]


def as_list(value: object) -> list[object]:
    """The value as the list it is."""
    assert a_list(value)
    return value


@needs_the_services
async def test_a_run_is_answered_as_it_starts_and_listed_while_it_plays(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The request answers the run `running`; its row is readable at once, and done once judged."""
    async with holding(gateway, tenant, agent):
        started = await gateway.http.post(
            "/v1/evals/run", json={"agent": agent, "goldens": [A_GOLDEN]}, headers=tenant.server
        )
        assert started.status_code == 200, started.text
        run = started.json()
        assert run["status"] == "running" and run["matrix"] is None
        # The row a 409 would name is there to read, not a ghost: the write committed on its own.
        shown = await gateway.http.get(f"/v1/evals/runs/{run['id']}", headers=tenant.server)
        assert shown.status_code == 200 and shown.json()["id"] == run["id"]
        done = await finished_run(gateway, tenant, run["id"])
    assert done["status"] == "done" and done["error"] is None
    assert [score["passed"] for score in cells_of(done)["saluda"]] == [True]
    assert goldens_opened(done) == ["saluda"]


@needs_the_services
async def test_a_golden_that_gives_memory_breaks_alone_on_an_agent_that_keeps_none(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """One golden's facts have nowhere to go: that cell breaks saying so, and the rest of the run plays."""
    async with holding(gateway, tenant, agent):
        started = await gateway.http.post(
            "/v1/evals/run",
            json={"agent": agent, "goldens": [A_REMEMBERING_GOLDEN, A_GOLDEN]},
            headers=tenant.server,
        )
        assert started.status_code == 200, started.text
        done = await finished_run(gateway, tenant, started.json()["id"])
    assert done["status"] == "done"
    cells = cells_of(done)
    (memory,) = cells["recuerda"]
    assert memory["metric"] == "memory" and memory["passed"] is False
    assert "memory policy" in str(memory["reason"])
    assert [score["passed"] for score in cells["saluda"]] == [True]
    # No call was opened for it: there was nothing to answer its facts with.
    assert goldens_opened(done) == ["saluda"]
