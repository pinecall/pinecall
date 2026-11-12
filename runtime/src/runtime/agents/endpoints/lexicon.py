"""An agent's lexicon per env and scope: read, written, and its history."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents import schemas
from runtime.agents.auth import KnownAgent, WordsKey
from runtime.agents.service import lexicon
from runtime.agents.service.versions import Written
from runtime.agents.settings import Lexicon
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/agents/{slug}/lexicon")
async def get_lexicon(slug: KnownAgent, actor: WordsKey, session: Session) -> schemas.LexiconResponse:
    """The agent's words as this key sees them: yours, the team's and production's."""
    return schemas.LexiconResponse.of(await lexicon.show_lexicon(session, actor.scope, slug))


# A supervisor's key may write it: the words are theirs to fix.
@router.put("/v1/agents/{slug}/lexicon")
async def put_lexicon(
    slug: KnownAgent, body: schemas.PutLexiconRequest, actor: WordsKey, session: Session
) -> schemas.LexiconResponse:
    """The agent's next lexicon in this scope or the team's."""
    wanted = Lexicon(said={item.word: item.spoken for item in body.lexicon.said}, heard=tuple(body.lexicon.heard))
    written = Written(author=actor.name, note=body.note, if_version=body.if_version)
    shown = await lexicon.put_lexicon(session, actor.scope, slug, wanted, written, team=body.team)
    return schemas.LexiconResponse.of(shown)


@router.get("/v1/agents/{slug}/lexicon/history")
async def list_lexicon_history(
    slug: KnownAgent, actor: WordsKey, session: Session, query: Annotated[schemas.HistoryQuery, Query()]
) -> schemas.LexiconHistoryResponse:
    """One scope's versions of the agent's lexicon, newest first."""
    history = await lexicon.list_lexicon_history(session, actor.scope, slug, team=query.team, limit=query.limit)
    return schemas.LexiconHistoryResponse.of(history)
