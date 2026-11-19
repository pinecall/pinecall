"""The insights endpoints a console draws from: tools, the slowest turns and the series' vendors."""

import time
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.models import CallFact, CallLogHead
from runtime.enums import Env
from runtime.wire.base import Entry
from tests.calls.factories import a_call_with_tools, a_tool_result, entry
from tests.conftest import Gateway, Tenant, needs_the_services
from tests.insights.folded import fold_call, opened

pytestmark = needs_the_services

A_WEEK = {"days": 7}


async def asked(gateway: Gateway, tenant: Tenant, path: str, **query: Any) -> dict[str, Any]:
    """The answer to a GET with the tenant's server key."""
    answer = await gateway.http.get(path, params=query, headers=tenant.server)
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def of(call: str, agent: str, entries: list[Entry]) -> list[Entry]:
    """The entries as that agent's call wrote them."""
    return [kept.model_copy(update={"call": call, "agent": agent}) for kept in entries]


async def test_the_tools_of_a_window_are_counted_ranked_and_carry_their_newest_failure(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    """book_slot failed twice and find_slots worked: the failing tool first, with the later error and its call."""
    await fold_call(sessions, tenant.org, a_call_with_tools(call, agent))
    body = await asked(gateway, tenant, "/v1/insights/tools", **A_WEEK)
    assert (body["days"], body["agent"]) == (7, None)
    booked, found = body["tools"]
    assert (booked["name"], booked["ran"], booked["failed"]) == ("book_slot", 2, 2)
    assert booked["last_error"] == {
        "call": call,
        "at": entry(14, "tool.result", {}).ts,
        "text": "book_slot did not answer within 10s",
    }
    assert booked["median_s"] == pytest.approx(0.2, rel=0.06)
    assert (found["name"], found["ran"], found["failed"], found["last_error"]) == ("find_slots", 1, 0, None)
    assert found["median_s"] == pytest.approx(0.4, rel=0.06)


async def test_the_tools_are_one_agents_when_the_window_names_it(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    """Another agent's tools stay out of an agent's window and in the scope's."""
    await fold_call(sessions, tenant.org, a_call_with_tools(call, agent))
    elsewhere = [entry(1, "tool.result", a_tool_result("tc_1", "cancel", seconds=0.1))]
    await fold_call(sessions, tenant.org, of(f"{call}-b", "other", elsewhere))
    mine = await asked(gateway, tenant, "/v1/insights/tools", agent=agent, **A_WEEK)
    assert [tool["name"] for tool in mine["tools"]] == ["book_slot", "find_slots"]
    every = await asked(gateway, tenant, "/v1/insights/tools", **A_WEEK)
    assert [tool["name"] for tool in every["tools"]] == ["book_slot", "cancel", "find_slots"]


async def test_the_slowest_turns_come_slowest_first_with_where_the_wait_went_and_a_limit(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    """Three kept for the call, two asked for: the slowest two, the first split into its parts."""
    await fold_call(sessions, tenant.org, a_call_with_tools(call, agent))
    body = await asked(gateway, tenant, "/v1/insights/slow", limit=2, **A_WEEK)
    first, second = body["turns"]
    assert first == {
        "call": call,
        "agent": agent,
        "seq": 7,
        "name": "Marta",
        "at": entry(7, "turn.agent", {}).ts,
        "e2e_s": 2.0,
        "hears_s": 0.2,
        "thinks_s": 0.5,
        "tools_s": pytest.approx(0.6),
        "speaks_s": 0.3,
    }
    assert (second["seq"], second["hears_s"], second["tools_s"]) == (10, None, None)
    assert len((await asked(gateway, tenant, "/v1/insights/slow", **A_WEEK))["turns"]) == 3


async def test_the_slowest_turns_are_refused_a_limit_out_of_range_and_a_window_that_is_not_one(
    gateway: Gateway, tenant: Tenant
) -> None:
    """limit is 1 to 50 and days one of 1, 7 or 30."""
    for query in ({"limit": 0}, {"limit": 51}, {"days": 3}):
        answer = await gateway.http.get("/v1/insights/slow", params=query, headers=tenant.server)
        assert answer.status_code in {400, 422}, (query, answer.text)


async def test_the_series_names_every_vendor_of_the_window_with_its_stage(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    """The voice of two turns on one vendor and model: one row of the window, with its turns and its median."""
    voiced = {"model_name": "flash", "model_provider": "elevenlabs"}
    turns = [
        entry(
            seq,
            "turn.agent",
            {
                "speech_id": f"s{seq}",
                "text": "buenas",
                "interrupted": False,
                "metrics": {"e2e_latency": 1.0, "tts_node_ttfb": 0.3, "tts_metadata": voiced},
            },
        )
        for seq in (1, 2)
    ]
    await fold_call(sessions, tenant.org, of(call, agent, turns))
    body = await asked(gateway, tenant, "/v1/insights/series", **A_WEEK)
    (spoken,) = [row for row in body["vendors"] if row["stage"] == "tts"]
    assert (spoken["vendor"], spoken["model"], spoken["turns"]) == ("elevenlabs", "flash", 2)
    assert spoken["median_s"] == pytest.approx(0.3, rel=0.06) and spoken["p95_s"] is not None
    assert len(body["series"]) == 7


# An operator opened a new org's agent: the list showed its seven calls and the ring over it said "0 calls
# in 30 days", because the window counted the reader's own copy alone (2026-11-17).
async def test_the_window_counts_the_copies_a_list_of_calls_reads(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    """The org's own copy and a colleague's both count for an admin in the sandbox; a server key counts the org's."""
    await opened(sessions, tenant.org, call, agent)
    await opened(sessions, tenant.org, f"{call}_theirs", agent, holder="m_a_colleague")
    asked_as = {"days": 7, "agent": agent}
    person = await gateway.http.get("/v1/insights", params=asked_as, headers=tenant.person)
    assert person.status_code == 200, person.text
    assert (person.json()["conversations"]["now"], person.json()["channels"]["web"]) == (2, 0)
    assert (await asked(gateway, tenant, "/v1/insights", **asked_as))["conversations"]["now"] == 1


# Until 2026-11-19 the window's `live` counted every call nobody had sealed, an email waiting for its answer too.
async def test_the_window_counts_as_live_the_calls_with_somebody_on_them(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    """A phone call going on is live; a written conversation open for hours is not, nor a head nobody wrote to."""
    going = {
        f"{call}_phone": "phone",
        f"{call}_whatsapp": "whatsapp",
        f"{call}_email": "email",
        f"{call}_unwritten": None,
    }
    async with sessions.begin() as session:
        for one, channel in going.items():
            session.add(
                CallLogHead(
                    log=one,
                    call=one,
                    agent=agent,
                    org=tenant.org,
                    env=Env.sandbox,
                    holder="",
                    started_at=time.time(),
                    seq=0 if channel is None else 3,
                )
            )
            await session.flush()
            if channel is not None:
                session.add(CallFact(call=one, channel=channel))
    window = await asked(gateway, tenant, "/v1/insights", days=7, agent=agent)
    assert (window["conversations"]["now"], window["live"]) == (4, 1)
