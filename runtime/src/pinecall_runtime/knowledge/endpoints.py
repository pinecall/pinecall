"""The knowledge and memory endpoints: bases and their files, a contact's facts, and the goldens."""

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from pinecall_runtime.accounts.service.attempts import AttemptThrottle
from pinecall_runtime.agents.auth import KnownAgent
from pinecall_runtime.agents.declaration import DEFAULT_CHUNKS_PER_TURN
from pinecall_runtime.agents.service import settings
from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.calls import service as calls
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import ReadKind
from pinecall_runtime.exceptions import NotFound, ServiceUnavailable, ValidationError
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.kit.time import now
from pinecall_runtime.knowledge import schemas
from pinecall_runtime.knowledge.auth import KnowledgeKey, MemoryKey
from pinecall_runtime.knowledge.service import bases, extraction, memory
from pinecall_runtime.knowledge.service.bases import Push, Question
from pinecall_runtime.knowledge.service.cutter import cut
from pinecall_runtime.knowledge.service.embedder import NO_EMBEDDER, Embedder, embedder_for
from pinecall_runtime.knowledge.service.language import language_of
from pinecall_runtime.knowledge.service.memory import GoldenQuestion
from pinecall_runtime.postgres import Session
from pinecall_runtime.providers import service as providers

router = APIRouter()

# Each run is up to fifty model calls: a suite runs once, a loop is stopped.
RUNS_A_MINUTE = 6


def _no_such_base(base: str) -> NotFound:
    # 404, not 204: dropping a mistyped name must not look like success.
    return NotFound(f"no knowledge base named {base}: nothing was pushed under that name")


def _no_such_file(base: str, path: str) -> NotFound:
    return NotFound(f"no file {path} in the base {base}")


# ── knowledge ──


@router.put("/v1/knowledge/{base}")
async def push_base(
    base: str, body: schemas.KnowledgePush, actor: KnowledgeKey, request: Request, session: Session
) -> schemas.KnowledgePushed:
    """Replace the base with the folder: cut, embedded where it changed, indexed."""
    started = time.perf_counter()
    embedder = await _embedder(request, session)
    push = Push(
        base=base,
        files=tuple(cut(item.path, item.text) for item in body.files),
        at=now(),
        language=language_of(body.language),
    )
    await bases.admit_push(session, actor.scope, push, path=None)
    language = await bases.put_base(session, embedder, actor.scope, push)
    return schemas.KnowledgePushed(
        base=base, chunks=push.chunks, language=language, took_ms=(time.perf_counter() - started) * 1000
    )


@router.get("/v1/knowledge")
async def list_bases(actor: KnowledgeKey, session: Session) -> schemas.KnowledgeList:
    """Every base the key's scope reads, its size, its model and when it was pushed."""
    return schemas.KnowledgeList(
        bases=[
            schemas.KnowledgeBase(
                base=item.base,
                chunks=item.chunks,
                model=item.model,
                language=item.language,
                pushed_at=item.pushed_at.timestamp(),
            )
            for item in await bases.list_bases(session, actor.scope)
        ]
    )


# Before `/{base}`, so "attached" is never read as a base's name.
@router.get("/v1/knowledge/attached")
async def attached_bases(actor: KnowledgeKey, session: Session) -> schemas.KnowledgeUses:
    """Each base some agent attaches, and the agents whose settings in the scope attach it."""
    readers: dict[str, list[str]] = {}
    for agent, tuning in sorted((await settings.every_tuning(session, actor.scope)).items()):
        for docs in tuning.bases or ():
            readers.setdefault(docs.base, []).append(agent)
    return schemas.KnowledgeUses(
        bases=[schemas.KnowledgeUse(base=base, agents=agents) for base, agents in sorted(readers.items())]
    )


@router.get("/v1/knowledge/{base}")
async def list_files(base: str, actor: KnowledgeKey, session: Session) -> schemas.KnowledgeFiles:
    """The base's files, each with its size and chunks, never its text."""
    listed = await bases.list_files(session, actor.scope, base)
    if listed is None:
        raise _no_such_base(base)
    return schemas.KnowledgeFiles(
        base=base,
        kept=bool(listed),
        files=[
            schemas.KnowledgeFileRow(
                path=item.path, chars=len(item.text), chunks=item.chunks, pushed_at=item.pushed_at.timestamp()
            )
            for item in listed
        ],
    )


@router.get("/v1/knowledge/{base}/files/{path:path}")
async def read_file(base: str, path: str, actor: KnowledgeKey, session: Session) -> schemas.KnowledgeFileRead:
    """One file of the base, text and all."""
    found = await bases.get_file(session, actor.scope, base, path)
    if found is None:
        raise _no_such_file(base, path)
    return schemas.KnowledgeFileRead(
        path=found.path, text=found.text, chunks=found.chunks, pushed_at=found.pushed_at.timestamp()
    )


@router.put("/v1/knowledge/{base}/files/{path:path}")
async def put_file(
    base: str, path: str, body: schemas.KnowledgeFilePut, actor: KnowledgeKey, request: Request, session: Session
) -> schemas.KnowledgeFilePushed:
    """Put one file into the base, beginning the base when there is none; only it is cut."""
    started = time.perf_counter()
    embedder = await _embedder(request, session)
    push = Push(base=base, files=(cut(path, body.text),), at=now())
    await bases.admit_push(session, actor.scope, push, path=path)
    language = await bases.put_file(session, embedder, actor.scope, push)
    return schemas.KnowledgeFilePushed(
        base=base, path=path, chunks=push.chunks, language=language, took_ms=(time.perf_counter() - started) * 1000
    )


@router.delete("/v1/knowledge/{base}/files/{path:path}", status_code=204)
async def drop_file(base: str, path: str, actor: KnowledgeKey, session: Session) -> None:
    """Take one file and its chunks out of the base, and the base with its last file."""
    if not await bases.drop_file(session, actor.scope, base, path):
        raise _no_such_file(base, path)


@router.delete("/v1/knowledge/{base}", status_code=204)
async def drop_base(base: str, actor: KnowledgeKey, session: Session) -> None:
    """Drop the holder's own copy of the base and its chunks."""
    if not await bases.drop_base(session, actor.scope, base):
        raise _no_such_base(base)


# Sequential: searches at once would measure the pool, not the index. No floor: the golden
# measures the ranking, not an attachment's threshold.
@router.post("/v1/knowledge/{base}/eval")
async def evaluate_base(
    base: str, body: schemas.KnowledgeGolden, actor: KnowledgeKey, request: Request, session: Session
) -> schemas.KnowledgeScore:
    """Ask the golden's questions of the base and score recall@k and nDCG@10, with no model."""
    embedder = await _embedder(request, session)
    found = next((item for item in await bases.list_bases(session, actor.scope) if item.base == base), None)
    if found is None:
        raise _no_such_base(base)
    k = body.k or DEFAULT_CHUNKS_PER_TURN
    started = time.perf_counter()
    score = await bases.ask_golden(
        session, embedder, actor.scope, base, [Question(item.asks, item.any_of) for item in body.questions], k
    )
    return schemas.KnowledgeScore(
        base=base,
        model=found.model,
        questions=score.questions,
        k=score.k,
        recall_at_k=score.figures.recall_at_k,
        ndcg_at_10=score.figures.ndcg_at_10,
        took_ms=(time.perf_counter() - started) * 1000,
        misses=[
            schemas.GoldenMiss(
                asks=miss.question.asks,
                expects=list(miss.question.expects),
                found=[chunk.where for chunk in miss.found],
            )
            for miss in score.misses
        ],
    )


# ── memory ──


# The whole history, superseded facts included; a call reads the current ones through `recall`.
@router.get("/v1/contacts/{contact}/memory")
async def contact_memory(contact: str, actor: MemoryKey, session: Session) -> schemas.ContactMemory:
    """Every fact ever kept of the contact, current first."""
    await compliance.record_read(session, actor.scope, contact, ReadKind.memory, by=_asked_by(actor))
    return schemas.ContactMemory(
        facts=[schemas.ContactFact.of(fact) for fact in await memory.history(session, actor.scope, contact)]
    )


# Reading and erasing are the contact's rights: no quota ever refuses them.
@router.delete("/v1/contacts/{contact}/memory")
async def forget_contact(contact: str, actor: MemoryKey, session: Session) -> schemas.Forgotten:
    """Every fact of the contact deleted, history included; zero is an answer, not a 404."""
    return schemas.Forgotten(forgotten=await memory.forget(session, actor.scope, contact))


@router.post("/v1/contacts/memory/eval")
async def memory_eval(
    body: schemas.MemoryGolden, actor: MemoryKey, request: Request, session: Session
) -> schemas.MemoryScore:
    """A memory golden asked of the ranking a call reads, on facts it writes and forgets."""
    embedder = await _embedder(request, session)
    questions = [GoldenQuestion(tuple(item.holds), item.asks, tuple(item.expects)) for item in body.questions]
    score = await memory.ask_golden(
        session, embedder, actor.scope, questions, body.k or memory.DEFAULT_FACTS_PER_TURN, at=now()
    )
    return schemas.MemoryScore(
        model=embedder.model,
        questions=score.questions,
        k=score.k,
        recall_at_k=score.figures.recall_at_k,
        ndcg_at_10=score.figures.ndcg_at_10,
        took_ms=score.took_ms,
        misses=[
            schemas.MemoryMiss(asks=item.question.asks, missing=list(item.missing), found=list(item.found))
            for item in score.misses
        ],
    )


@router.get("/v1/agents/{slug}/memory")
async def agent_memory(
    slug: KnownAgent, actor: MemoryKey, session: Session, page: Annotated[schemas.MemoryPage, Query()]
) -> schemas.AgentMemory:
    """The current facts the agent's calls taught, across contacts, newest first, a page."""
    await compliance.record_read(session, actor.scope, slug, ReadKind.memory, by=_asked_by(actor))
    found = await calls.facts_taught_by(session, actor.scope, slug, after=page.after, q=page.q, limit=page.limit)
    return schemas.AgentMemory(
        facts=[
            schemas.AgentFact(
                id=str(fact.id),
                contact=fact.contact,
                text=fact.text,
                category=fact.category,
                written_at=fact.valid_from.timestamp(),
            )
            for fact in found.facts
        ],
        next=found.next,
    )


@router.get("/v1/memory")
async def org_memory(
    actor: MemoryKey, session: Session, page: Annotated[schemas.MemoryPage, Query()]
) -> schemas.OrgMemory:
    """The current facts every agent's calls taught, each with its agent, newest first, a page."""
    await compliance.record_read(session, actor.scope, actor.org, ReadKind.memory, by=_asked_by(actor))
    found = await calls.facts_taught_by(session, actor.scope, None, after=page.after, q=page.q, limit=page.limit)
    return schemas.OrgMemory(
        facts=[
            schemas.OrgFact(
                id=str(fact.id),
                agent=found.agents[str(fact.id)],
                contact=fact.contact,
                text=fact.text,
                category=fact.category,
                written_at=fact.valid_from.timestamp(),
            )
            for fact in found.facts
        ],
        next=found.next,
    )


# The row stays, ended: the history still shows it. Erasing a contact is compliance's endpoint.
@router.delete("/v1/memory/facts/{id}")
async def forget_fact(
    fact: Annotated[uuid.UUID, Path(alias="id")], actor: MemoryKey, session: Session
) -> schemas.Forgotten:
    """One current fact ended from now on; 404 when there is none by that id."""
    if not await memory.invalidate(session, actor.scope, fact, at=now()):
        # One sentence for a fact missing, already ended, or another org's: nothing is told apart.
        raise NotFound(f"no current fact {fact} in this key's org and env")
    return schemas.Forgotten(forgotten=1)


# Here and not in the CLI: the agent's model, the org's keys and the tuned policy live here.
@router.post("/v1/agents/{slug}/memory/extraction")
async def memory_extraction(
    slug: KnownAgent, body: schemas.ExtractionCases, actor: MemoryKey, request: Request, session: Session
) -> schemas.ExtractionRun:
    """One hang-up per case on the agent's own model and keys, each answer judged by code."""
    await AttemptThrottle(request.app.state.sessions, RUNS_A_MINUTE).check(
        f"{actor.org} memory/extraction", "extraction runs from this org"
    )
    registry: AgentRegistry = request.app.state.registry
    registration = registry.holder_of(actor.scope, slug)
    if registration is None or registration.scope.org != actor.org:
        raise NotFound(f"no app holds agent {slug}: start one, or deploy it")
    catalog = await providers.get_catalog(session)
    config, _ = await settings.tuned_for_call(session, registration.config, actor.scope, catalog)
    policy = config.memory
    if policy is None or not policy.remember:
        # A 400, not an empty pass: a green run for a feature the agent lacks would mislead.
        raise ValidationError(
            f"agent {slug} remembers nothing: its memory policy names nothing to keep (pinecall memory policy "
            f"--remember '…')"
        )
    for case in body.cases:
        extraction.check_case(case, policy)
    vault: Vault = handles_of(request).vault
    model = providers.thinking_of(config, catalog, await providers.keys_of(session, vault, actor.scope))
    tools = tuple(tool.name for tool in config.tools)
    started = time.perf_counter()
    # One after the other: side by side would measure the vendor's concurrency.
    results = [await extraction.extract_case(model, case, policy=policy, tools=tools, at=now()) for case in body.cases]
    return schemas.ExtractionRun(
        agent=slug,
        model=model.vendor if model.model is None else f"{model.vendor}/{model.model}",
        cases=len(results),
        held=sum(item.held for item in results),
        took_ms=(time.perf_counter() - started) * 1000,
        results=results,
    )


# ── private ──


# Built per request from the row and the box's keys, so an edited row takes from the next request.
async def _embedder(request: Request, session: Session) -> Embedder:
    vault: Vault = handles_of(request).vault
    catalog = await providers.get_catalog(session)
    embedder = embedder_for(catalog, await providers.box_credentials(session, vault), handles_of(request).http)
    if embedder is None:
        raise ServiceUnavailable(NO_EMBEDDER)
    return embedder


# The one record of who asked, which is what audits a read and an erasure.
def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id
