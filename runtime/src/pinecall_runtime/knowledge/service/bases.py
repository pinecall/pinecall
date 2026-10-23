"""Knowledge bases: listed, pushed, searched as a turn searches them, and held to a golden."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.billing import service as billing
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.knowledge.models import KnowledgeBase, KnowledgeFile
from pinecall_runtime.knowledge.repository import ChunkToWrite, FileToWrite, KnowledgeRepository
from pinecall_runtime.knowledge.service import ranking
from pinecall_runtime.knowledge.service.cutter import (
    HEADING_JOINT,
    Cut,
    answers,
    body_of,
    indexed_text,
    where,
)
from pinecall_runtime.knowledge.service.embedder import Embedder, WrongModel, halfvec
from pinecall_runtime.knowledge.service.language import BY_NAME, UNDECIDED, Language, detected
from pinecall_runtime.knowledge.service.ranking import Evidence, Figures
from pinecall_runtime.postgres import unbounded


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


@dataclass(frozen=True, slots=True)
class Written:
    """What a push left: the language the base speaks, and how many of its files the push did not touch."""

    language: Language
    kept: int


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """What a search asks: the words, how many chunks at most, and each base with its floor."""

    query: str
    k: int
    # A chunk's fused score must reach its own base's floor; 0.0 is none.
    bases: Mapping[str, float]
    # The query's vector, where the caller embedded it already (a golden embeds its questions at once).
    vector: list[float] | None = None


@dataclass(frozen=True, slots=True)
class Found:
    """One chunk found: where it is, its body, its score in this search, its cosine."""

    id: str
    base: str
    path: str
    heading: str | None
    text: str
    score: float
    cosine: float

    @property
    def where(self) -> str:
        """The chunk's file, then its heading path."""
        return where(self.path, self.heading)


@dataclass(frozen=True, slots=True)
class Searched:
    """What a search found, and how strongly its best cosine says the answer is there."""

    found: list[Found]
    evidence: Evidence
    model: str


@dataclass(frozen=True, slots=True)
class Question:
    """A golden question and the heading paths any one of which answers it."""

    asks: str
    expects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Answered:
    """A question and the chunks the search handed back, best first."""

    question: Question
    found: list[Found]


@dataclass(frozen=True, slots=True)
class Score:
    """A golden run: how many questions, at which k, its two figures, and the questions missed."""

    questions: int
    k: int
    figures: Figures
    misses: list[Answered]


async def list_bases(session: AsyncSession, scope: Scope) -> Sequence[KnowledgeBase]:
    """The holder's bases, and the org's where the holder has pushed none of that name."""
    return await KnowledgeRepository(session).bases_read_by(scope)


async def list_files(session: AsyncSession, scope: Scope, base: str) -> Sequence[KnowledgeFile] | None:
    """Every file of the copy the holder reads, by path; None when there is no such base."""
    repository = KnowledgeRepository(session)
    copy = await repository.copy_read_by(scope, base)
    if copy is None:
        return None
    return await repository.files_of(copy.org, copy.env, copy.holder, base)


async def get_file(session: AsyncSession, scope: Scope, base: str, path: str) -> KnowledgeFile | None:
    """One file of the copy the holder reads, with its text."""
    repository = KnowledgeRepository(session)
    copy = await repository.copy_read_by(scope, base)
    if copy is None:
        return None
    found = await repository.files_of(copy.org, copy.env, copy.holder, base, path)
    return found[0] if found else None


# A push is sized whole before a row is written: what the org keeps in this env, less what the
# push takes out (the files it names, or the whole base when it replaces it), plus what it was cut into.
async def admit_push(session: AsyncSession, scope: Scope, push: Push, *, paths: Sequence[str] | None) -> None:
    """Refuse a push that would take the org past its chunks quota; `paths` are the files it replaces, None the base."""
    repository = KnowledgeRepository(session)
    kept = await repository.chunks_kept_by_org(scope.org, scope.env)
    replaced = await repository.chunks_in(scope, push.base, paths=paths)
    await billing.admit_push(session, scope.org, scope.env, keeping=kept - replaced + push.chunks)


async def put_base(session: AsyncSession, embedder: Embedder, scope: Scope, push: Push) -> Language:
    """Replace the holder's base with the push, only the files whose text changed embedded; the language it speaks."""
    written = await _written(session, embedder, scope, push, keep=[item.path for item in push.files])
    return written.language


# Files put beside others must sit in the space those were embedded in: under another model the
# base is pushed whole, with replace, and every file is embedded again.
async def put_files(session: AsyncSession, embedder: Embedder, scope: Scope, push: Push) -> Written:
    """Put the push's files into the base by path, keeping its others and beginning it when there is none."""
    own = await KnowledgeRepository(session).own(scope, push.base)
    if own is not None and own.model != embedder.model:
        raise WrongModel(push.base, own.model, embedder.model)
    return await _written(session, embedder, scope, push, keep=None)


async def put_file(session: AsyncSession, embedder: Embedder, scope: Scope, push: Push) -> Language:
    """Put the push's file beside the base's others, beginning the base when there is none; the language it speaks."""
    return (await put_files(session, embedder, scope, push)).language


async def drop_base(session: AsyncSession, scope: Scope, base: str) -> bool:
    """Drop the holder's own copy of the base and its chunks; False when it has none."""
    return await KnowledgeRepository(session).drop(scope, base)


async def drop_file(session: AsyncSession, scope: Scope, base: str, path: str) -> bool:
    """Drop one file of the holder's own copy, and the base with its last file."""
    return await KnowledgeRepository(session).drop_file(scope, base, path)


async def chunks_kept(session: AsyncSession, org: str, env: Env) -> int:
    """How many chunks the org keeps in the env, every holder's."""
    return await KnowledgeRepository(session).chunks_kept_by_org(org, env)


# Every base in one ranking: fused scores compare only within one, and searched one base at a
# time, an irrelevant base takes a turn's slots with a 1.0 of its own.
async def search(session: AsyncSession, embedder: Embedder, scope: Scope, query: SearchQuery) -> Searched:
    """The best chunks of every base asked, each over its own floor, at most k."""
    repository = KnowledgeRepository(session)
    copies = await repository.copies_read_by(scope, list(query.bases))
    for copy in copies:
        if copy.model != embedder.model:
            raise WrongModel(copy.base, copy.model, embedder.model)
    if not copies:
        return Searched(found=[], evidence="none", model=embedder.model)
    [vector] = [query.vector] if query.vector is not None else await embedder.embed([query.query])
    room = ranking.CANDIDATES_PER_BRANCH * len(copies)
    hits = await repository.search(scope, copies, vector=halfvec(vector), words=query.query, room=room)
    floored = [hit for hit in ranking.relative_to_the_best(hits) if hit.fused >= query.bases[hit.row["base"]]]
    chosen = ranking.sections_chosen([hit.row for hit in floored], query.k)
    texts = await repository.section_texts(scope, [floored[at].row for at in chosen])
    found = [
        Found(
            id=floored[at].id,
            base=floored[at].row["base"],
            path=floored[at].row["path"],
            heading=floored[at].row["heading"],
            text=HEADING_JOINT.join(
                body_of(text, floored[at].row["heading"]) for text in texts.get(place, [floored[at].row["text"]])
            ),
            score=floored[at].fused,
            cosine=floored[at].cosine,
        )
        for place, at in enumerate(chosen)
    ]
    return Searched(found=found, evidence=ranking.evidence_of(ranking.top_cosine(hits)), model=embedder.model)


# Every question embedded in one go, then each searched with the base alone at full weight: what
# a turn would have found, without a round trip to the embedder per question.
async def ask_golden(
    session: AsyncSession, embedder: Embedder, scope: Scope, base: str, questions: Sequence[Question], k: int
) -> Score:
    """Each question asked of the base, and recall@k and nDCG@10 over every answer."""
    vectors = await embedder.embed([question.asks for question in questions])
    answered: list[Answered] = []
    for question, vector in zip(questions, vectors, strict=True):
        asked = SearchQuery(query=question.asks, k=k, bases={base: 0.0}, vector=vector)
        answered.append(Answered(question, (await search(session, embedder, scope, asked)).found))
    return score_docs(answered, k)


def score_docs(answered: Sequence[Answered], k: int) -> Score:
    """Recall at k and nDCG at 10 over every question, and the ones whose chunk never came back."""
    ranks = [_rank(item) for item in answered]
    return Score(
        questions=len(answered),
        k=k,
        figures=ranking.figures([[rank] for rank in ranks]),
        misses=[item for item, rank in zip(answered, ranks, strict=True) if rank is None],
    )


# A hash is only worth its vectors under the model that wrote them: under another, every file is
# embedded again. The vendor answers before the statement runs, so no connection waits on it.
async def _written(
    session: AsyncSession, embedder: Embedder, scope: Scope, push: Push, *, keep: list[str] | None
) -> Written:
    repository = KnowledgeRepository(session)
    own = await repository.own(scope, push.base)
    had: Sequence[KnowledgeFile] = ()
    if own is not None:
        had = await repository.files_of(scope.org, scope.env, scope.holder, push.base)
    language = push.language or _language_kept(own, keep) or detected(_texts_of(push, had, keep))
    known: dict[str, str] = {}
    if own is not None and own.model == embedder.model:
        known = {file.path: file.sha256 for file in had}
    changed = [item for item in push.files if known.get(item.path) != item.sha256]
    documents = [[indexed_text(piece) for piece in item.pieces] for item in changed if item.pieces]
    embedded = await embedder.embed_documents(documents) if documents else []
    pieces = [piece for item in changed for piece in item.pieces]
    vectors = [vector for document in embedded for vector in document]
    chunks = [
        ChunkToWrite(
            path=piece.path, heading=piece.heading, ordinal=piece.ordinal, text=indexed_text(piece), embedding=vector
        )
        for piece, vector in zip(pieces, vectors, strict=True)
    ]
    # A question is embedded alone, as a query is, so it sits in the space the questions arrive in.
    asked = [(piece, question) for piece in pieces for question in piece.asks]
    answers_vectors = await embedder.embed([question for _, question in asked]) if asked else []
    chunks += [
        ChunkToWrite(
            path=piece.path, heading=piece.heading, ordinal=piece.ordinal, text=question, embedding=vector, kind="ask"
        )
        for (piece, question), vector in zip(asked, answers_vectors, strict=True)
    ]
    files = [FileToWrite(path=item.path, text=item.text, sha256=item.sha256, chunks=item.rows) for item in changed]
    # Unbounded: a base of thousands of chunks is that many rows into two indexes.
    async with unbounded(session):
        await repository.write(
            scope,
            push.base,
            model=embedder.model,
            dimensions=embedder.embedding.dimensions,
            language=language,
            at=push.at,
            keep=keep,
            changed=files,
            chunks=chunks,
        )
    pushed = {item.path for item in push.files}
    return Written(language=language, kept=0 if keep is not None else sum(file.path not in pushed for file in had))


# One file put beside the others speaks the base's language; a folder pushed whole says its own. A
# base whose files said no language clearly is counted again with every file put, so one that
# began with a table of names speaks the language of the prose put beside it.
def _language_kept(own: KnowledgeBase | None, keep: list[str] | None) -> Language | None:
    if own is None or keep is not None or own.language == UNDECIDED:
        return None
    return BY_NAME[own.language]


# What the language is counted from: the folder pushed, or the file put and the files it joins.
def _texts_of(push: Push, had: Sequence[KnowledgeFile], keep: list[str] | None) -> list[str]:
    pushed = {item.path: item.text for item in push.files}
    kept = {} if keep is not None else {file.path: file.text for file in had}
    return list({**kept, **pushed}.values())


# Only the first match counts: a base that repeats itself answered once, and any of the paths answers.
def _rank(item: Answered) -> int | None:
    return next(
        (
            at
            for at, chunk in enumerate(item.found, start=1)
            if any(answers(chunk.where, expected) for expected in item.question.expects)
        ),
        None,
    )
