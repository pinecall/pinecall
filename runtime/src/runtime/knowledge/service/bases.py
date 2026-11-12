"""Knowledge bases: listed, read, pushed whole or a file at a time, and dropped."""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.billing import service as billing
from runtime.enums import Env
from runtime.exceptions import NotFound, ServiceUnavailable
from runtime.kit.time import now
from runtime.knowledge.models import ChunkKind, KnowledgeBase, KnowledgeFile, Language
from runtime.knowledge.repository import BaseWrite, ChunkToWrite, FileToWrite, KnowledgeRepository
from runtime.knowledge.service.cutter import Cut, cut, text_for_index
from runtime.knowledge.service.embedder import Embedder
from runtime.knowledge.service.language import UNDECIDED, detect_language, parse_language
from runtime.postgres import without_timeouts


class NoSuchBase(NotFound):
    """Nothing was pushed under that name in the scope."""

    # 404, not 204: dropping a mistyped name must not look like success.
    def __init__(self, base: str) -> None:
        super().__init__(f"no knowledge base named {base}: nothing was pushed under that name")


class NoSuchFile(NotFound):
    """The base holds no file by that path."""

    def __init__(self, base: str, path: str) -> None:
        super().__init__(f"no file {path} in the base {base}")


class WrongModel(ServiceUnavailable):
    """A base was embedded by another model than the box runs now."""

    def __init__(self, base: str, written_by: str, running: str) -> None:
        super().__init__(
            f"base {base} was embedded by {written_by} and this box embeds with {running}: push it again "
            "so its vectors are in the model's space"
        )


@dataclass(frozen=True, slots=True)
class Push:
    """What a push writes into a base: the files as cut, and when it was pushed."""

    base: str
    files: tuple[Cut, ...]
    at: datetime
    # The language the push says; None is counted from the files' words, or kept from the base.
    language: Language | None = None

    @property
    def chunks(self) -> int:
        """How many rows the files become: their pieces and the questions those answer, each a chunk of the quota."""
        return sum(item.rows for item in self.files)

    @property
    def paths(self) -> list[str]:
        """The paths of the files it carries."""
        return [item.path for item in self.files]


@dataclass(frozen=True, slots=True)
class Pushed:
    """What a push left: the base, its chunks, the files it did not touch, its language, how long it took."""

    base: str
    chunks: int
    # How many files of the base the push did not name and left as they were; 0 on a replace.
    kept: int
    language: Language
    took_ms: float


@dataclass(frozen=True, slots=True)
class FilePut:
    """What one file put into a base left: the file, its chunks, the base's language, how long it took."""

    base: str
    path: str
    chunks: int
    language: Language
    took_ms: float


@dataclass(frozen=True, slots=True)
class Attached:
    """One base and the agents whose settings attach it."""

    base: str
    agents: list[str]


# What a push reads before the vendor is asked, so that no connection waits on it.
@dataclass(frozen=True, slots=True)
class _Plan:
    language: Language
    # The files whose text changed, or every file where another model wrote the base.
    changed: tuple[Cut, ...]
    # How many of the base's files the push does not name and leaves as they are.
    kept: int


async def list_bases(session: AsyncSession, scope: Scope) -> Sequence[KnowledgeBase]:
    """The holder's bases, and the org's where the holder has pushed none of that name."""
    return await KnowledgeRepository(session).list_read_by(scope)


async def get_base(session: AsyncSession, scope: Scope, base: str) -> KnowledgeBase:
    """The copy of the base the holder reads: its own, else the org's; refused when there is neither."""
    copy = await KnowledgeRepository(session).find_read_by(scope, base)
    if copy is None:
        raise NoSuchBase(base)
    return copy


# Off each agent's newest settings in the scope: a base only its class attaches is not listed.
async def list_attached(session: AsyncSession, scope: Scope) -> list[Attached]:
    """Each base some agent attaches, and the agents whose settings in the scope attach it."""
    readers: dict[str, list[str]] = {}
    for agent, settings in sorted((await agents.list_settings(session, scope)).items()):
        for docs in settings.bases or ():
            readers.setdefault(docs.base, []).append(agent)
    return [Attached(base=base, agents=named) for base, named in sorted(readers.items())]


async def list_files(session: AsyncSession, scope: Scope, base: str) -> Sequence[KnowledgeFile]:
    """Every file of the copy the holder reads, by path; refused when there is no such base."""
    return await KnowledgeRepository(session).list_files(await get_base(session, scope, base))


async def get_file(session: AsyncSession, scope: Scope, base: str, path: str) -> KnowledgeFile:
    """One file of the copy the holder reads, with its text; refused when the base holds none by that path."""
    repository = KnowledgeRepository(session)
    copy = await repository.find_read_by(scope, base)
    found = None if copy is None else await repository.find_file(copy, path)
    if found is None:
        raise NoSuchFile(base, path)
    return found


# By path: a file of the base the push does not name is kept, so a file the console put stays
# through `docs push`; `replace` is the folder as the one truth, as a repository's push is.
async def push_folder(
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    scope: Scope,
    base: str,
    files: Sequence[tuple[str, str]],
    *,
    language: str | None,
    replace: bool,
) -> Pushed:
    """Put the folder's files into the base, keeping its others; with `replace` the base becomes the folder."""
    started = time.perf_counter()
    push = Push(
        base=base,
        files=tuple(cut(path, text) for path, text in files),
        at=now(),
        language=parse_language(language),
    )
    plan = await _write(sessions, embedder, scope, push, replace=replace)
    return Pushed(base=base, chunks=push.chunks, kept=plan.kept, language=plan.language, took_ms=_since(started))


async def put_file(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, base: str, path: str, text: str
) -> FilePut:
    """Put one file beside the base's others, beginning the base when there is none; only it is cut."""
    started = time.perf_counter()
    push = Push(base=base, files=(cut(path, text),), at=now())
    plan = await _write(sessions, embedder, scope, push, replace=False)
    return FilePut(base=base, path=path, chunks=push.chunks, language=plan.language, took_ms=_since(started))


async def delete_base(session: AsyncSession, scope: Scope, base: str) -> None:
    """Drop the holder's own copy of the base and its chunks; refused when it has none."""
    if not await KnowledgeRepository(session).delete_own(scope, base):
        raise NoSuchBase(base)


async def delete_file(session: AsyncSession, scope: Scope, base: str, path: str) -> None:
    """Drop one file of the holder's own copy and its chunks, and the base with its last file."""
    repository = KnowledgeRepository(session)
    if not await repository.delete_file(scope, base, path):
        raise NoSuchFile(base, path)
    own = await repository.find_own(scope, base)
    if own is None:
        return
    if await repository.list_files(own):
        await repository.recount(scope, own)
    else:
        await repository.delete(own)


async def count_chunks(session: AsyncSession, org: str, env: Env) -> int:
    """How many chunks the org keeps in the env, every holder's."""
    return await KnowledgeRepository(session).count_chunks_of_org(org, env)


# ── private ──


# Three steps, and no connection held across the second: what the base holds is read and the push
# admitted, the vendor embeds what changed, the rows are written. Until 2026-11 the one transaction of
# the request stayed open while the vendor answered, a window of 24 000 tokens at a time: past the
# minute a transaction may sit idle, Postgres closed it, and the push failed at its end with the vendor
# already paid.
async def _write(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, push: Push, *, replace: bool
) -> _Plan:
    async with sessions.begin() as session:
        plan = await _plan(session, embedder.model, scope, push, replace=replace)
    chunks = await _embed(embedder, plan.changed)
    files = [FileToWrite(path=item.path, text=item.text, sha256=item.sha256, chunks=item.rows) for item in plan.changed]
    wanted = BaseWrite(
        base=push.base,
        model=embedder.model,
        dimensions=embedder.embedding.dimensions,
        language=plan.language,
        at=push.at,
        keep=push.paths if replace else None,
        changed=files,
        chunks=chunks,
    )
    # No timeout: a base of thousands of chunks is that many rows into two indexes.
    async with sessions.begin() as session, without_timeouts(session):
        await _admit(session, scope, push, replace=replace)
        await KnowledgeRepository(session).write(scope, wanted)
    return plan


# Files put beside others must sit in the space those were embedded in: under another model the
# base is pushed whole, with replace, and every file is embedded again. A hash is only worth its
# vectors under the model that wrote them: under another, every file is embedded again.
async def _plan(session: AsyncSession, model: str, scope: Scope, push: Push, *, replace: bool) -> _Plan:
    await _admit(session, scope, push, replace=replace)
    repository = KnowledgeRepository(session)
    own = await repository.find_own(scope, push.base)
    if own is not None and own.model != model and not replace:
        raise WrongModel(push.base, own.model, model)
    had: Sequence[KnowledgeFile] = () if own is None else await repository.list_files(own)
    language = push.language or _keep_language(own, replace=replace) or detect_language(_texts_of(push, had, replace))
    known: dict[str, str] = {}
    if own is not None and own.model == model:
        known = {file.path: file.sha256 for file in had}
    pushed = set(push.paths)
    return _Plan(
        language=language,
        changed=tuple(item for item in push.files if known.get(item.path) != item.sha256),
        kept=0 if replace else sum(file.path not in pushed for file in had),
    )


# A push is sized whole before a row is written: what the org keeps in this env, less what the push
# takes out (the files it names, or the whole base when it replaces it), plus what it was cut into.
# The stock is held while it is counted, so two pushes at the limit are counted in turn: once before
# the vendor is asked, so a push past the limit costs nothing, and again in the transaction that writes.
async def _admit(session: AsyncSession, scope: Scope, push: Push, *, replace: bool) -> None:
    await billing.hold_stock(session, scope.org, scope.env, "knowledge_chunks")
    repository = KnowledgeRepository(session)
    kept = await repository.count_chunks_of_org(scope.org, scope.env)
    replaced = await repository.count_chunks_in(scope, push.base, paths=None if replace else push.paths)
    await billing.admit_push(session, scope.org, scope.env, keeping=kept - replaced + push.chunks)


async def _embed(embedder: Embedder, changed: Sequence[Cut]) -> list[ChunkToWrite]:
    documents = [[text_for_index(piece) for piece in item.pieces] for item in changed if item.pieces]
    embedded = await embedder.embed_documents(documents) if documents else []
    pieces = [piece for item in changed for piece in item.pieces]
    vectors = [vector for document in embedded for vector in document]
    chunks = [
        ChunkToWrite(
            path=piece.path, heading=piece.heading, ordinal=piece.ordinal, text=text_for_index(piece), embedding=vector
        )
        for piece, vector in zip(pieces, vectors, strict=True)
    ]
    # A question is embedded alone, as a query is, so it sits in the space the questions arrive in.
    asked = [(piece, question) for piece in pieces for question in piece.asks]
    answers = await embedder.embed([question for _, question in asked]) if asked else []
    return chunks + [
        ChunkToWrite(
            path=piece.path,
            heading=piece.heading,
            ordinal=piece.ordinal,
            text=question,
            embedding=vector,
            kind=ChunkKind.ask,
        )
        for (piece, question), vector in zip(asked, answers, strict=True)
    ]


# One file put beside the others speaks the base's language; a folder pushed whole says its own. A
# base whose files said no language clearly is counted again with every file put, so one that
# began with a table of names speaks the language of the prose put beside it.
def _keep_language(own: KnowledgeBase | None, *, replace: bool) -> Language | None:
    if own is None or replace or own.language == UNDECIDED:
        return None
    return own.language


# What the language is counted from: the folder pushed, or the file put and the files it joins.
def _texts_of(push: Push, had: Sequence[KnowledgeFile], replace: bool) -> list[str]:
    pushed = {item.path: item.text for item in push.files}
    kept = {} if replace else {file.path: file.text for file in had}
    return list({**kept, **pushed}.values())


def _since(started: float) -> float:
    return (time.perf_counter() - started) * 1000
