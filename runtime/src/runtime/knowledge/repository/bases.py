"""The knowledge tables: bases, their files and their chunks, in one scope and the org's copy beneath it."""

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, RowMapping, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import distinct_on

from runtime.actor import THE_ORGS_OWN, Scope
from runtime.enums import Env
from runtime.kit.repository import Repository
from runtime.knowledge.models import ChunkKind, KnowledgeBase, KnowledgeChunk, KnowledgeFile, Language
from runtime.knowledge.repository.search import ChunkFound, Hit, HybridQuery, Lexical, hybrid

# A found chunk comes back as its section: the chunks of its heading this many either side of it.
SECTION_SPAN = 2
# What a search reads of a chunk is what `ChunkFound` holds, by the columns' own names.
CHUNK_COLUMNS = tuple(one.name for one in dataclasses.fields(ChunkFound))


# Each copy is a pair of equalities the planner estimates from the column statistics. Asked as a
# join on two unnested arrays, it guessed a hundred rows for a copy of six thousand, chose to score
# every row of the copy by hand over the two index scans, and a search took a second (2026-10-22).
def knowledge_scope(copies: int) -> str:
    """The rows of these copies of the org's bases in the env, one `(base, holder)` pair each."""
    pairs = " OR ".join(f"(base = :base_{at} AND holder = :holder_{at})" for at in range(copies))
    return f"org = :org AND env = :env AND ({pairs})"


# The chunks around each found one, under the same heading of the same file, in the file's order;
# a question found hands back the text it sits beside, never itself.
SECTIONS = text("""
SELECT wanted.at, chunk.text
FROM unnest(CAST(:ats AS integer[]), CAST(:bases AS text[]), CAST(:holders AS text[]), CAST(:paths AS text[]),
    CAST(:headings AS text[]), CAST(:firsts AS integer[]), CAST(:lasts AS integer[]))
    AS wanted (at, base, holder, path, heading, first, last)
JOIN knowledge_chunks AS chunk ON chunk.org = :org AND chunk.env = :env
    AND chunk.base = wanted.base AND chunk.holder = wanted.holder AND chunk.path = wanted.path
    AND chunk.heading IS NOT DISTINCT FROM wanted.heading
    AND chunk.ordinal BETWEEN wanted.first AND wanted.last
    AND chunk.kind = 'text'
ORDER BY wanted.at, chunk.ordinal
""")


# One partial BM25 index a language (migrations/versions/…000007), read where its predicate is
# repeated. A language is one of the closed set, so it is written into the statement, where a
# bound parameter would hide the predicate from the planner.
def lexical_of(language: Language) -> Lexical:
    """The index of the chunks in this language, and the rows it covers."""
    return Lexical(f"knowledge_chunks_{language.value}_bm25", f"language = '{language.value}'")


@dataclass(frozen=True, slots=True)
class ChunkToWrite:
    """One row as the write inserts it: a piece of text, or a question the piece at that ordinal answers."""

    path: str
    heading: str | None
    ordinal: int
    text: str
    embedding: list[float]
    kind: ChunkKind = ChunkKind.text


@dataclass(frozen=True, slots=True)
class FileToWrite:
    """One file as the write upserts it."""

    path: str
    text: str
    sha256: str
    chunks: int


@dataclass(frozen=True, slots=True)
class BaseWrite:
    """A push as it is written into the holder's own copy of a base: its row, the files that changed, their chunks."""

    base: str
    model: str
    dimensions: int
    language: Language
    at: datetime
    # The paths the base keeps and no other; None keeps every file the push does not name.
    keep: Sequence[str] | None
    changed: Sequence[FileToWrite]
    chunks: Sequence[ChunkToWrite]


class KnowledgeRepository(Repository[KnowledgeBase]):
    """Bases, their files and their chunks, in one scope and the org's copy beneath it."""

    model = KnowledgeBase

    # '' sorts before any member id: ordering holder DESC puts the holder's own copy first, so a
    # read falls back to the org's copy and a write never does.
    async def list_read_by(self, scope: Scope) -> Sequence[KnowledgeBase]:
        """The holder's bases, and the org's where the holder has pushed none of that name."""
        statement = (
            self.statement()
            .where(*_read_by(scope))
            .order_by(KnowledgeBase.base, KnowledgeBase.holder.desc())
            .ext(distinct_on(KnowledgeBase.base))
        )
        return await self.all(statement)

    async def find_read_by(self, scope: Scope, base: str) -> KnowledgeBase | None:
        """The copy of the base the holder reads: its own, else the org's."""
        statement = (
            self.statement()
            .where(*_read_by(scope), KnowledgeBase.base == base)
            .order_by(KnowledgeBase.holder.desc())
            .limit(1)
        )
        return await self.one_or_none(statement)

    async def list_copies_read_by(self, scope: Scope, bases: Sequence[str]) -> Sequence[KnowledgeBase]:
        """Each named base's copy the holder reads."""
        statement = (
            self.statement()
            .where(*_read_by(scope), KnowledgeBase.base.in_(list(bases)))
            .order_by(KnowledgeBase.base, KnowledgeBase.holder.desc())
            .ext(distinct_on(KnowledgeBase.base))
        )
        return await self.all(statement)

    async def find_own(self, scope: Scope, base: str) -> KnowledgeBase | None:
        """The holder's own copy of the base, never the org's."""
        return await self.one_or_none(self.statement().where(*_own(scope, base)))

    async def list_files(self, copy: KnowledgeBase) -> Sequence[KnowledgeFile]:
        """The files of one copy, by path."""
        statement = select(KnowledgeFile).where(*_files_of(copy)).order_by(KnowledgeFile.path)
        return (await self.session.execute(statement)).scalars().all()

    async def find_file(self, copy: KnowledgeBase, path: str) -> KnowledgeFile | None:
        """One file of one copy."""
        statement = select(KnowledgeFile).where(*_files_of(copy), KnowledgeFile.path == path)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def count_chunks_of_org(self, org: str, env: Env) -> int:
        """How many chunks the org keeps in the env, every holder's: what the quota counts."""
        statement = select(func.coalesce(func.sum(KnowledgeBase.chunks), 0)).where(
            KnowledgeBase.org == org, KnowledgeBase.env == env
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def count_chunks_in(self, scope: Scope, base: str, *, paths: Sequence[str] | None = None) -> int:
        """How many chunks the holder's own copy of the base holds, or these files of it."""
        statement = select(func.count()).select_from(KnowledgeChunk).where(*_own_chunks(scope, base))
        if paths is not None:
            statement = statement.where(KnowledgeChunk.path.in_(list(paths)))
        return int((await self.session.execute(statement)).scalar_one())

    # One transaction: the base's row, the chunks of what changed or left, the files, the new
    # chunks, then the count read back exact.
    async def write(self, scope: Scope, wanted: BaseWrite) -> KnowledgeBase:
        """Write a push into the holder's own copy, beginning the base when there is none."""
        row = await self._put_row(scope, wanted)
        await self._delete_what_left(scope, wanted)
        await self._put_files(row, wanted)
        self.session.add_all(
            [
                KnowledgeChunk(
                    org=scope.org,
                    env=scope.env,
                    holder=scope.holder,
                    base=wanted.base,
                    path=chunk.path,
                    heading=chunk.heading,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    embedding=chunk.embedding,
                    language=wanted.language,
                    kind=chunk.kind,
                )
                for chunk in wanted.chunks
            ]
        )
        await self.session.flush()
        return await self.recount(scope, row)

    async def recount(self, scope: Scope, row: KnowledgeBase) -> KnowledgeBase:
        """Set the base's count to the chunks its copy holds now."""
        return await self.update(row, chunks=await self.count_chunks_in(scope, row.base))

    async def delete_own(self, scope: Scope, base: str) -> bool:
        """Drop the holder's own copy of the base; chunks and files cascade. False when none."""
        row = await self.find_own(scope, base)
        if row is None:
            return False
        await self.delete(row)
        return True

    async def delete_file(self, scope: Scope, base: str, path: str) -> bool:
        """Drop one file of the holder's own copy and its chunks. False when the copy holds none by that path."""
        dropped = await self.change(delete(KnowledgeFile).where(*_own_files(scope, base), KnowledgeFile.path == path))
        if not dropped:
            return False
        await self.change(delete(KnowledgeChunk).where(*_own_chunks(scope, base), KnowledgeChunk.path == path))
        return True

    async def search(
        self, scope: Scope, copies: Sequence[KnowledgeBase], *, vector: Sequence[float], words: str, room: int
    ) -> list[Hit[ChunkFound]]:
        """The hybrid search over the chunks of these copies."""
        params: dict[str, Any] = {"org": scope.org, "env": scope.env.value}
        for at, copy in enumerate(copies):
            params[f"base_{at}"], params[f"holder_{at}"] = copy.base, copy.holder
        query = HybridQuery(
            table="knowledge_chunks",
            columns=CHUNK_COLUMNS,
            scope=knowledge_scope(len(copies)),
            params=params,
            lexical=[lexical_of(language) for language in dict.fromkeys(copy.language for copy in copies)],
            vector=vector,
            words=words,
            room=room,
        )
        return await hybrid(self.session, query, _read_chunk)

    async def list_section_texts(self, scope: Scope, found: Sequence[ChunkFound]) -> dict[int, list[str]]:
        """Each found chunk's section as its chunks' indexed texts in the file's order, by the chunk's place."""
        if not found:
            return {}
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "ats": list(range(len(found))),
            "bases": [chunk.base for chunk in found],
            "holders": [chunk.holder for chunk in found],
            "paths": [chunk.path for chunk in found],
            "headings": [chunk.heading for chunk in found],
            "firsts": [chunk.ordinal - SECTION_SPAN for chunk in found],
            "lasts": [chunk.ordinal + SECTION_SPAN for chunk in found],
        }
        texts: dict[int, list[str]] = {}
        for at, section in (await self.session.execute(SECTIONS, params)).all():
            texts.setdefault(int(at), []).append(str(section))
        return texts

    async def _put_row(self, scope: Scope, wanted: BaseWrite) -> KnowledgeBase:
        row = await self.find_own(scope, wanted.base)
        if row is None:
            return await self.add(
                KnowledgeBase(
                    org=scope.org,
                    env=scope.env,
                    holder=scope.holder,
                    base=wanted.base,
                    model=wanted.model,
                    dimensions=wanted.dimensions,
                    language=wanted.language,
                    chunks=0,
                    pushed_at=wanted.at,
                )
            )
        if row.language != wanted.language:
            # The chunks kept move to the new language's index with the base; nothing is embedded again.
            moved = update(KnowledgeChunk).where(*_own_chunks(scope, wanted.base)).values(language=wanted.language)
            await self.change(moved)
        return await self.update(
            row, model=wanted.model, dimensions=wanted.dimensions, language=wanted.language, pushed_at=wanted.at
        )

    # The chunks of every file the push changed, and with `keep` the files it no longer carries and theirs.
    async def _delete_what_left(self, scope: Scope, wanted: BaseWrite) -> None:
        gone: ColumnElement[bool] = KnowledgeChunk.path.in_([file.path for file in wanted.changed])
        if wanted.keep is not None:
            gone = gone | KnowledgeChunk.path.not_in(list(wanted.keep))
            left = KnowledgeFile.path.not_in(list(wanted.keep))
            await self.change(delete(KnowledgeFile).where(*_own_files(scope, wanted.base), left))
        await self.change(delete(KnowledgeChunk).where(*_own_chunks(scope, wanted.base), gone))

    async def _put_files(self, row: KnowledgeBase, wanted: BaseWrite) -> None:
        kept = {file.path: file for file in await self.list_files(row)}
        for file in wanted.changed:
            found = kept.get(file.path)
            if found is None:
                self.session.add(
                    KnowledgeFile(
                        org=row.org,
                        env=row.env,
                        holder=row.holder,
                        base=row.base,
                        path=file.path,
                        text=file.text,
                        chunks=file.chunks,
                        sha256=file.sha256,
                        pushed_at=wanted.at,
                    )
                )
            else:
                found.text, found.chunks, found.sha256, found.pushed_at = file.text, file.chunks, file.sha256, wanted.at


def _read_chunk(row: RowMapping) -> ChunkFound:
    return ChunkFound(**{column: row[column] for column in CHUNK_COLUMNS})


def _read_by(scope: Scope) -> tuple[Any, ...]:
    return (
        KnowledgeBase.org == scope.org,
        KnowledgeBase.env == scope.env,
        KnowledgeBase.holder.in_([scope.holder, THE_ORGS_OWN]),
    )


def _own(scope: Scope, base: str) -> tuple[Any, ...]:
    return (
        KnowledgeBase.org == scope.org,
        KnowledgeBase.env == scope.env,
        KnowledgeBase.holder == scope.holder,
        KnowledgeBase.base == base,
    )


def _files_of(copy: KnowledgeBase) -> tuple[Any, ...]:
    return (
        KnowledgeFile.org == copy.org,
        KnowledgeFile.env == copy.env,
        KnowledgeFile.holder == copy.holder,
        KnowledgeFile.base == copy.base,
    )


def _own_files(scope: Scope, base: str) -> tuple[Any, ...]:
    return (
        KnowledgeFile.org == scope.org,
        KnowledgeFile.env == scope.env,
        KnowledgeFile.holder == scope.holder,
        KnowledgeFile.base == base,
    )


def _own_chunks(scope: Scope, base: str) -> tuple[Any, ...]:
    return (
        KnowledgeChunk.org == scope.org,
        KnowledgeChunk.env == scope.env,
        KnowledgeChunk.holder == scope.holder,
        KnowledgeChunk.base == base,
    )
