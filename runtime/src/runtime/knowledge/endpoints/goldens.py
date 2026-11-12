"""The three goldens over HTTP: a base, memory and a hang-up's extraction, each held to its questions."""

from fastapi import APIRouter

from runtime.agents.declaration import DEFAULT_CHUNKS_PER_TURN
from runtime.handles import TheSessions, TheVault
from runtime.knowledge import schemas
from runtime.knowledge.auth import KnowledgeKey, MemoryKey, TheEmbedder, TheHeldSlug, an_extraction_run_a_time
from runtime.knowledge.service import base_golden, extraction_golden, memory_golden
from runtime.knowledge.service.memory import DEFAULT_FACTS_PER_TURN

router = APIRouter()


@router.post("/v1/knowledge/{base}/eval")
async def run_base_golden(
    base: str, body: schemas.KnowledgeGolden, actor: KnowledgeKey, embedder: TheEmbedder, sessions: TheSessions
) -> schemas.KnowledgeScore:
    """Ask the golden's questions of the base and score recall@k and nDCG@10, with no model."""
    questions = [base_golden.Question(item.asks, item.any_of) for item in body.questions]
    k = body.k or DEFAULT_CHUNKS_PER_TURN
    return schemas.KnowledgeScore.of(await base_golden.run(sessions, embedder, actor.scope, base, questions, k))


@router.post("/v1/contacts/memory/eval")
async def run_memory_golden(
    body: schemas.MemoryGolden, actor: MemoryKey, embedder: TheEmbedder, sessions: TheSessions
) -> schemas.MemoryScore:
    """A memory golden asked of the ranking a call reads, on facts it writes and forgets."""
    questions = [memory_golden.Question(tuple(item.holds), item.asks, tuple(item.expects)) for item in body.questions]
    k = body.k or DEFAULT_FACTS_PER_TURN
    return schemas.MemoryScore.of(await memory_golden.run(sessions, embedder, actor.scope, questions, k))


@router.post("/v1/agents/{slug}/memory/extraction", dependencies=[an_extraction_run_a_time])
async def run_extraction_golden(
    slug: TheHeldSlug, body: schemas.ExtractionCases, actor: MemoryKey, sessions: TheSessions, vault: TheVault
) -> schemas.ExtractionRun:
    """One hang-up per case on the agent's own model and keys, each answer judged by code."""
    cases = [_case_of(item) for item in body.cases]
    return schemas.ExtractionRun.of(await extraction_golden.run(sessions, vault, actor.scope, slug, cases))


def _case_of(item: schemas.ExtractionGolden) -> extraction_golden.Case:
    expect = item.expect
    return extraction_golden.Case(
        name=item.name,
        said=tuple(item.said),
        holds=tuple(item.holds),
        plants=tuple(item.plants),
        channel=item.channel,
        expect=extraction_golden.Expected(
            writes=tuple(expect.writes),
            never=tuple(expect.never),
            never_says=tuple(expect.never_says),
            invalidates=tuple(expect.invalidates),
        ),
    )
