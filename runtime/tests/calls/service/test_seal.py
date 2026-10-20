"""How a call ends: the judges that found it broken are said on the org's feed, by name and nothing else."""

import asyncio

from pinecall_runtime.calls.logs import Logs
from pinecall_runtime.calls.service import seal
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.scores import CallScore, Judgment, JudgmentEvidence
from tests.conftest import needs_the_database

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
