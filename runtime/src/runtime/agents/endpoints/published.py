"""What an agent's app publishes for pages: lines recorded in its voice, an output its model explains, and documents."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response

from runtime.agents import schemas
from runtime.agents.auth import KnownAgent, PublishingKey, TheDocument, TheOwner
from runtime.agents.service import documents, explain, lines
from runtime.enums import Env
from runtime.handles import TheSessions, TheVault
from runtime.postgres import Session

router = APIRouter()

MP3 = "audio/mpeg"
# A line's id is the hash of what it holds, so its audio never changes under the same URL.
FOREVER = "public, max-age=31536000, immutable"
# A document changes when its app publishes again: a page reads a new one within a minute.
A_MINUTE = "public, max-age=60"


# Recorded with the voice the agent's next call in this env would speak with. The use case opens its
# own transactions: none is held while the vendor speaks.
@router.post("/v1/agents/{slug}/lines")
async def record_lines(
    slug: KnownAgent,
    body: schemas.RecordLinesRequest,
    actor: PublishingKey,
    request: Request,
    sessions: TheSessions,
    vault: TheVault,
) -> schemas.RecordedLines:
    """Each text as a line in the agent's voice, recorded once and kept: the ones recorded before cost nothing."""
    base = str(request.base_url).rstrip("/")
    recorded = await lines.record_lines(sessions, vault, actor.scope, slug, body.texts, base)
    return schemas.RecordedLines(lines=[schemas.RecordedLine.of(line) for line in recorded])


# Explained by the model the agent's next call in this env would think with, on the same keys as a call.
@router.post("/v1/agents/{slug}/explain")
async def explain_output(
    slug: KnownAgent, body: schemas.ExplainRequest, actor: PublishingKey, sessions: TheSessions, vault: TheVault
) -> schemas.Explained:
    """A text a page shows, explained by the agent's model as notes, each on one line of it."""
    asked = explain.Asked(output=body.output, command=body.command or "", language=body.language, most=body.most)
    notes = await explain.explain_output(sessions, vault, actor.scope, slug, asked)
    return schemas.Explained(notes=[schemas.Note.of(note) for note in notes])


@router.get("/v1/lines/{name}")
async def get_line_audio(name: str, session: Session) -> Response:
    """A recorded line's MP3, by the id it is kept under, for any page; it never changes."""
    audio = await lines.get_audio(session, name.removesuffix(".mp3"))
    return Response(audio, media_type=MP3, headers={"Cache-Control": FOREVER})


@router.put("/v1/agents/{slug}/public/{name}")
async def publish_document(
    slug: KnownAgent, name: str, actor: PublishingKey, raw: TheDocument, session: Session
) -> dict[str, Any]:
    """Publish a JSON object under a name for any page to read, over the one before it."""
    return await documents.publish_document(session, actor.scope, slug, name, raw)


# No key: the agent's org is the one its log belongs to; another env or a slug nobody holds is 404.
@router.get("/v1/agents/{slug}/public/{name}")
async def read_document(
    slug: str, name: str, org: TheOwner, session: Session, env: Annotated[Env, Query()] = Env.production
) -> Response:
    """A document the agent's app published, for any page, with no key."""
    body = await documents.get_document(session, org=org, env=env, agent=slug, name=name)
    return Response(json.dumps(body), media_type="application/json", headers={"Cache-Control": A_MINUTE})
