"""How a call ends: its summary from a log that may be unreadable, and the judges that found it broken said by name."""

import asyncio
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.logs import Log, Logs
from pinecall_runtime.calls.schemas import SealCallRequest
from pinecall_runtime.calls.service import seal
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.scores import CallScore, Judgment, JudgmentEvidence
from tests.conftest import needs_the_database, until

pytestmark = needs_the_database


def judged(name: str, verdict: str) -> Judgment:
    """One judge's answer, with a reason and evidence a feed must never carry."""
    return Judgment.model_validate(
        {
            "name": name,
            "verdict": verdict,
            "criteria": "c",
            "reason": "she gave the dni 12345678Z",
            "evidence": JudgmentEvidence(seqs=[3], said="12345678Z").model_dump(),
        }
    )


async def test_each_broken_judge_is_said_once_with_the_call_and_nothing_of_why(
    store: Store, call: str, agent: str
) -> None:
    """A held judge and a skipped one are not news; two broken ones are, by name."""
    logs = Logs(store)
    scope = Scope("clinica", Env.sandbox)
    feed = await logs.feed_reader("clinica", Env.sandbox)
    score = CallScore(
        judges=[
            judged("polite", "held"),
            judged("promises", "broken"),
            judged("skips", "skipped"),
            judged("dni", "broken"),
        ],
        judge_calls=4,
    )
    seal.announce_broken_judges(logs, scope, call, agent, score)
    said = [await asyncio.wait_for(anext(feed), 2.0) for _ in range(2)]
    assert [(entry.type, entry.ephemeral, entry.data) for entry in said] == [
        ("judge.broke", True, {"call": call, "agent": agent, "judge": "promises"}),
        ("judge.broke", True, {"call": call, "agent": agent, "judge": "dni"}),
    ]
    feed.close()
    assert [entry async for entry in feed] == []


A_START: JsonObject = {
    "channel": "web",
    "direction": "inbound",
    "from": "web_1",
    "to": "clinica-norte",
    "started_at": 1.0,
}
AN_END: JsonObject = {"reason": "caller_hung_up", "ended_by": "caller", "ended_at": 5.0, "duration_s": 4.0}


async def summary_of(
    store: Store,
    sessions: async_sessionmaker[AsyncSession],
    call: str,
    agent: str,
    entries: list[tuple[str, JsonObject]],
) -> JsonObject:
    """The call.summary the seal writes over a log of these entries, written however the log was taken."""
    for kind, data in entries:
        await store.append(call, agent, kind, data, ephemeral=False)
    async with sessions.begin() as session:
        await seal.sum_up(session, store, Log(store, call, agent), SealCallRequest(usage=[], outcome="done"))
    return next(entry.data for entry in await store.whole(call) if entry.type == "call.summary")


# M B10 (2026-10-23): a call.started with no `caller` (required, `Contact | null`) was taken, and its
# seal answered 500 on every try. The endpoints refuse it now; a log written before may hold one.
async def test_a_call_whose_start_has_no_caller_is_summed_up_from_what_it_did_write(
    store: Store, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    summary = await summary_of(store, sessions, call, agent, [("call.started", A_START), ("call.ended", AN_END)])
    assert (summary["reason"], summary["duration_s"], summary["simulated"]) == ("caller_hung_up", 4.0, False)
    assert summary.get("run") is None


async def test_a_call_whose_end_cannot_be_read_is_summed_up_as_one_that_ended_in_error(
    store: Store, sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    broken = {**AN_END, "reason": "of its own accord"}
    summary = await summary_of(
        store, sessions, call, agent, [("call.started", {**A_START, "caller": None}), ("call.ended", broken)]
    )
    assert (summary["reason"], summary["duration_s"]) == ("error", 0.0)


# A renewal that raised ended the loop: the lease lapsed under a seal still running, and another gateway
# took it over (the summary and the score are guarded to be written once, but the work was done twice).
async def test_a_renewal_of_the_seals_lease_that_failed_is_said_and_tried_again(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    renewed = 0

    class Renewing:
        async def renew_seal(self, _call: str, _seconds: float) -> None:
            nonlocal renewed
            renewed += 1
            if renewed == 1:
                raise RuntimeError("the database did not answer")

    monkeypatch.setattr(seal, "LEASED_S", 0.03)
    renewing = asyncio.create_task(seal._renew(cast(Store, Renewing()), "call_1"))
    try:
        await until(lambda: renewed >= 3, 30)
        assert not renewing.done()
        assert "renewing a seal's lease failed on call_1" in caplog.text
    finally:
        renewing.cancel()
        await asyncio.gather(renewing, return_exceptions=True)
