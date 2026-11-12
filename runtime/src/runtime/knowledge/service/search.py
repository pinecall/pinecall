"""The search a turn runs over its agent's bases: every base in one ranking, a hit handed back as its section."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.knowledge.models import KnowledgeBase
from runtime.knowledge.repository import ChunkFound, KnowledgeRepository
from runtime.knowledge.service import ranking
from runtime.knowledge.service.bases import WrongModel
from runtime.knowledge.service.cutter import HEADING_JOINT, body_of, where
from runtime.knowledge.service.embedder import Embedder

# The best pages give every section that was found in them; every page after them gives one.
PAGES_GIVING_ALL = 2


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """What a search asks: the words, how many chunks at most, and each base with its floor."""

    query: str
    k: int
    # A chunk's fused score must reach its own base's floor; 0.0 is none.
    bases: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class Found:
    """One chunk found: where it is, its body, its score in this search."""

    id: str
    base: str
    path: str
    heading: str | None
    text: str
    score: float

    @property
    def where(self) -> str:
        """The chunk's file, then its heading path."""
        return where(self.path, self.heading)


# The vendor is asked between two short transactions, so no connection waits on it. Until 2026-11 a
# turn's lookup held one of the pool's connections through the embedder's round trip, three tries of it.
async def search(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, query: SearchQuery
) -> list[Found]:
    """The best chunks of every base asked, each over its own floor, at most k."""
    async with sessions.begin() as session:
        copies = await list_copies(session, scope, list(query.bases), embedder.model)
    if not copies:
        return []
    [vector] = await embedder.embed([query.query])
    async with sessions.begin() as session:
        return await search_by_vector(session, scope, copies, query, vector)


async def list_copies(session: AsyncSession, scope: Scope, bases: Sequence[str], model: str) -> Sequence[KnowledgeBase]:
    """The copy the holder reads of each base asked, every one in the model's space; WrongModel otherwise."""
    copies = await KnowledgeRepository(session).list_copies_read_by(scope, bases)
    for copy in copies:
        if copy.model != model:
            raise WrongModel(copy.base, copy.model, model)
    return copies


# Every base in one ranking: fused scores compare only within one, and searched one base at a
# time, an irrelevant base takes a turn's slots with a 1.0 of its own.
async def search_by_vector(
    session: AsyncSession, scope: Scope, copies: Sequence[KnowledgeBase], query: SearchQuery, vector: Sequence[float]
) -> list[Found]:
    """The search over these copies for a query whose vector is in hand: a golden embeds its questions at once."""
    repository = KnowledgeRepository(session)
    room = ranking.CANDIDATES_PER_BRANCH * len(copies)
    hits = await repository.search(scope, copies, vector=vector, words=query.query, room=room)
    floored = [hit for hit in ranking.relative_to_the_best(hits) if hit.fused >= query.bases[hit.row.base]]
    chosen = [floored[at] for at in choose_sections([hit.row for hit in floored], query.k)]
    texts = await repository.list_section_texts(scope, [hit.row for hit in chosen])
    return [
        Found(
            id=hit.id,
            base=hit.row.base,
            path=hit.row.path,
            heading=hit.row.heading,
            text=HEADING_JOINT.join(body_of(text, hit.row.heading) for text in texts.get(place, [hit.row.text])),
            score=hit.fused,
        )
        for place, hit in enumerate(chosen)
    ]


def choose_sections(chunks: Sequence[ChunkFound], k: int) -> list[int]:
    """Which hits come back, best first: one per section, the best pages all theirs, k at most."""
    chosen: list[int] = []
    sections: set[tuple[str, str, str | None]] = set()
    pages: list[tuple[str, str]] = []
    for at, chunk in enumerate(chunks):
        page = (chunk.base, chunk.path)
        section = (chunk.base, chunk.path, chunk.heading)
        if section in sections or (page in pages and pages.index(page) >= PAGES_GIVING_ALL):
            continue
        if page not in pages:
            pages.append(page)
        sections.add(section)
        chosen.append(at)
        if len(chosen) == k:
            break
    return chosen
