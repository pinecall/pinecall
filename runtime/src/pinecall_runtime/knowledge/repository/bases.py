"""The knowledge tables: bases, their files and their chunks, in one scope and the org's copy beneath it."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, delete, func, select, text
from sqlalchemy.dialects.postgresql import distinct_on

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.knowledge.models import KnowledgeBase, KnowledgeChunk, KnowledgeFile
from pinecall_runtime.knowledge.repository.search import Hit, hybrid

KNOWLEDGE_TEXT_INDEX = "knowledge_chunks_text_bm25"
# A found chunk comes back as its section: the chunks of its heading this many either side of it.
SECTION_SPAN = 2

KNOWLEDGE_SCOPE = """
org = :org AND env = :env AND (base, holder) IN (
    SELECT copy.base, copy.holder FROM unnest(CAST(:bases AS text[]), CAST(:holders AS text[])) AS copy (base, holder)
)
"""

# The chunks around each found one, under the same heading of the same file, in the file's order.
SECTIONS = text("""
SELECT wanted.at, chunk.text
FROM unnest(CAST(:ats AS integer[]), CAST(:bases AS text[]), CAST(:holders AS text[]), CAST(:paths AS text[]),
    CAST(:headings AS text[]), CAST(:firsts AS integer[]), CAST(:lasts AS integer[]))
    AS wanted (at, base, holder, path, heading, first, last)
JOIN knowledge_chunks AS chunk ON chunk.org = :org AND chunk.env = :env
    AND chunk.base = wanted.base AND chunk.holder = wanted.holder AND chunk.path = wanted.path
    AND chunk.heading IS NOT DISTINCT FROM wanted.heading
    AND chunk.ordinal BETWEEN wanted.first AND wanted.last
ORDER BY wanted.at, chunk.ordinal
""")

KNOWLEDGE_COLUMNS = ("base", "holder", "path", "heading", "ordinal", "text")


@dataclass(frozen=True, slots=True)
class ChunkToWrite:
    """One chunk as the write inserts it."""

    path: str
    heading: str | None
    ordinal: int
    text: str
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class FileToWrite:
    """One file as the write upserts it."""

    path: str
    text: str
    sha256: str
    chunks: int


class KnowledgeRepository(Repository[KnowledgeBase]):
    """Bases, their files and their chunks, in one scope and the org's copy beneath it."""

    model = KnowledgeBase

    # '' sorts before any member id: ordering holder DESC puts the holder's own copy first, so a
    # read falls back to the org's copy and a write never does.
    async def bases_read_by(self, scope: Scope) -> Sequence[KnowledgeBase]:
        """The holder's bases, and the org's where the holder has pushed none of that name."""
        statement = (
            self.statement()
            .where(
                KnowledgeBase.org == scope.org,
                KnowledgeBase.env == scope.env,
                KnowledgeBase.holder.in_([scope.holder, ""]),
            )
            .order_by(KnowledgeBase.base, KnowledgeBase.holder.desc())
            .ext(distinct_on(KnowledgeBase.base))
        )
        return await self.all(statement)

    async def copy_read_by(self, scope: Scope, base: str) -> KnowledgeBase | None:
        """The copy of the base the holder reads: its own, else the org's."""
        statement = (
            self.statement()
            .where(
                KnowledgeBase.org == scope.org,
                KnowledgeBase.env == scope.env,
                KnowledgeBase.holder.in_([scope.holder, ""]),
                KnowledgeBase.base == base,
            )
            .order_by(KnowledgeBase.holder.desc())
            .limit(1)
        )
        return await self.one_or_none(statement)

    async def copies_read_by(self, scope: Scope, bases: Sequence[str]) -> Sequence[KnowledgeBase]:
        """Each named base's copy the holder reads."""
        statement = (
            self.statement()
            .where(
                KnowledgeBase.org == scope.org,
                KnowledgeBase.env == scope.env,
                KnowledgeBase.holder.in_([scope.holder, ""]),
                KnowledgeBase.base.in_(list(bases)),
            )
            .order_by(KnowledgeBase.base, KnowledgeBase.holder.desc())
            .ext(distinct_on(KnowledgeBase.base))
        )
        return await self.all(statement)

    async def own(self, scope: Scope, base: str) -> KnowledgeBase | None:
        """The holder's own copy of the base, never the org's."""
        return await self.one_or_none(self.statement().where(*_owned(scope, base)))

    async def files_of(
        self, org: str, env: Env, holder: str, base: str, path: str | None = None
    ) -> Sequence[KnowledgeFile]:
        """The files of one copy, by path; one file when a path is named."""
        statement = select(KnowledgeFile).where(
            KnowledgeFile.org == org,
            KnowledgeFile.env == env,
            KnowledgeFile.holder == holder,
            KnowledgeFile.base == base,
        )
        if path is not None:
            statement = statement.where(KnowledgeFile.path == path)
        return (await self.session.execute(statement.order_by(KnowledgeFile.path))).scalars().all()

    async def chunks_kept_by_org(self, org: str, env: Env) -> int:
        """How many chunks the org keeps in the env, every holder's: what the quota counts."""
        statement = select(func.coalesce(func.sum(KnowledgeBase.chunks), 0)).where(
            KnowledgeBase.org == org, KnowledgeBase.env == env
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def chunks_in(self, scope: Scope, base: str, *, path: str | None = None) -> int:
        """How many chunks the holder's own copy of the base holds, or one file of it."""
        statement = select(func.count()).select_from(KnowledgeChunk).where(*_owned_chunks(scope, base))
        if path is not None:
            statement = statement.where(KnowledgeChunk.path == path)
        return int((await self.session.execute(statement)).scalar_one())

    # One transaction: the base's row, the chunks of what changed or left, the files, the new
    # chunks, then the count read back exact. `keep` None keeps every other file.
    async def write(
        self,
        scope: Scope,
        base: str,
        *,
        model: str,
        dimensions: int,
        at: datetime,
        keep: Sequence[str] | None,
        changed: Sequence[FileToWrite],
        chunks: Sequence[ChunkToWrite],
    ) -> KnowledgeBase:
        """Write a push into the holder's own copy, beginning the base when there is none."""
        row = await self.own(scope, base)
        if row is None:
            row = await self.add(
                KnowledgeBase(
                    org=scope.org,
                    env=scope.env,
                    holder=scope.holder,
                    base=base,
                    model=model,
                    dimensions=dimensions,
                    chunks=0,
                    pushed_at=at,
                )
            )
        else:
            await self.update(row, model=model, dimensions=dimensions, pushed_at=at)
        changed_paths = [file.path for file in changed]
        gone: ColumnElement[bool] = KnowledgeChunk.path.in_(changed_paths)
        if keep is not None:
            gone = gone | KnowledgeChunk.path.not_in(list(keep))
            await self.session.execute(
                delete(KnowledgeFile).where(*_owned_files(scope, base), KnowledgeFile.path.not_in(list(keep)))
            )
        await self.session.execute(delete(KnowledgeChunk).where(*_owned_chunks(scope, base), gone))
        kept_files = {file.path: file for file in await self.files_of(scope.org, scope.env, scope.holder, base)}
        for file in changed:
            found = kept_files.get(file.path)
            if found is None:
                self.session.add(
                    KnowledgeFile(
                        org=scope.org,
                        env=scope.env,
                        holder=scope.holder,
                        base=base,
                        path=file.path,
                        text=file.text,
                        chunks=file.chunks,
                        sha256=file.sha256,
                        pushed_at=at,
                    )
                )
            else:
                found.text, found.chunks, found.sha256, found.pushed_at = file.text, file.chunks, file.sha256, at
        self.session.add_all(
            [
                KnowledgeChunk(
                    org=scope.org,
                    env=scope.env,
                    holder=scope.holder,
                    base=base,
                    path=chunk.path,
                    heading=chunk.heading,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    embedding=chunk.embedding,
                )
                for chunk in chunks
            ]
        )
        await self.session.flush()
        return await self.update(row, chunks=await self.chunks_in(scope, base))

    async def drop(self, scope: Scope, base: str) -> bool:
        """Drop the holder's own copy of the base; chunks and files cascade. False when none."""
        row = await self.own(scope, base)
        if row is None:
            return False
        await self.delete(row)
        return True

    async def drop_file(self, scope: Scope, base: str, path: str) -> bool:
        """Drop one file of the holder's own copy and its chunks, and the base with its last file."""
        files = await self.files_of(scope.org, scope.env, scope.holder, base, path)
        if not files:
            return False
        await self.session.execute(
            delete(KnowledgeChunk).where(*_owned_chunks(scope, base), KnowledgeChunk.path == path)
        )
        await self.session.delete(files[0])
        await self.session.flush()
        row = await self.own(scope, base)
        if row is not None:
            left = await self.files_of(scope.org, scope.env, scope.holder, base)
            if left:
                await self.update(row, chunks=await self.chunks_in(scope, base))
            else:
                await self.delete(row)
        return True

    async def search(
        self, scope: Scope, copies: Sequence[KnowledgeBase], *, vector: str, words: str, room: int
    ) -> list[Hit]:
        """The hybrid search over the chunks of these copies."""
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "bases": [copy.base for copy in copies],
            "holders": [copy.holder for copy in copies],
        }
        return await hybrid(
            self.session,
            "knowledge_chunks",
            KNOWLEDGE_TEXT_INDEX,
            KNOWLEDGE_SCOPE,
            "true",
            KNOWLEDGE_COLUMNS,
            params,
            vector=vector,
            words=words,
            room=room,
        )

    async def section_texts(self, scope: Scope, rows: Sequence[Mapping[str, Any]]) -> dict[int, list[str]]:
        """Each row's section as its chunks' indexed texts in the file's order, by the row's place."""
        if not rows:
            return {}
        ordinals = [int(row["ordinal"]) for row in rows]
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "ats": list(range(len(rows))),
            "bases": [row["base"] for row in rows],
            "holders": [row["holder"] for row in rows],
            "paths": [row["path"] for row in rows],
            "headings": [row["heading"] for row in rows],
            "firsts": [ordinal - SECTION_SPAN for ordinal in ordinals],
            "lasts": [ordinal + SECTION_SPAN for ordinal in ordinals],
        }
        texts: dict[int, list[str]] = {}
        for at, found in (await self.session.execute(SECTIONS, params)).all():
            texts.setdefault(int(at), []).append(str(found))
        return texts


def _owned(scope: Scope, base: str) -> tuple[Any, ...]:
    return (
        KnowledgeBase.org == scope.org,
        KnowledgeBase.env == scope.env,
        KnowledgeBase.holder == scope.holder,
        KnowledgeBase.base == base,
    )


def _owned_files(scope: Scope, base: str) -> tuple[Any, ...]:
    return (
        KnowledgeFile.org == scope.org,
        KnowledgeFile.env == scope.env,
        KnowledgeFile.holder == scope.holder,
        KnowledgeFile.base == base,
    )


def _owned_chunks(scope: Scope, base: str) -> tuple[Any, ...]:
    return (
        KnowledgeChunk.org == scope.org,
        KnowledgeChunk.env == scope.env,
        KnowledgeChunk.holder == scope.holder,
        KnowledgeChunk.base == base,
    )
