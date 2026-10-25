"""What an agent's app publishes for pages: lines recorded in its voice, and documents, both read with no key."""

import json
from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request, Response

from pinecall_runtime.agents import schemas
from pinecall_runtime.agents.auth import KnownAgent, PublishingKey, registry_of
from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service import documents, lines, settings
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.kit.http import capped_body
from pinecall_runtime.postgres import Session
from pinecall_runtime.providers import service as providers

router = APIRouter()

MP3 = "audio/mpeg"
# A line's id is the hash of what it holds, so its audio never changes under the same URL.
FOREVER = "public, max-age=31536000, immutable"
# A document changes when its app publishes again: a page reads a new one within a minute.
A_MINUTE = "public, max-age=60"
NOT_AN_OBJECT = "a document is one JSON object"
NO_SUCH_AGENT = "no agent {slug} here"


# Recorded with the voice the agent's next call in this env would speak with: its settings over its
# class, the providers row, and the org's keys or the box's lent ones.
@router.post("/v1/agents/{slug}/lines")
async def record_lines(
    slug: KnownAgent, body: schemas.RecordLinesRequest, actor: PublishingKey, request: Request, session: Session
) -> schemas.RecordedLines:
    """Each text as a line in the agent's voice, recorded once and kept: the ones recorded before cost nothing."""
    registration = registry_of(request).holder_of(actor.scope, slug)
    declared = AgentConfig(slug=slug) if registration is None else registration.config
    catalog = await providers.get_catalog(session)
    config, _ = await settings.tuned_for_call(session, declared, actor.scope, catalog)
    keys = await providers.keys_of(session, handles_of(request).vault, actor.scope)
    running = providers.build_pipeline(config, catalog, keys).tts
    rows = await lines.record_lines(
        session, org=actor.org, env=actor.env, agent=slug, texts=body.texts, running=running, says=config.says
    )
    base = str(request.base_url).rstrip("/")
    return schemas.RecordedLines(
        lines=[
            schemas.RecordedLine(
                id=row.id,
                text=row.text,
                url=f"{base}/v1/lines/{row.id}.mp3",
                duration_ms=row.duration_ms,
                voice=row.voice,
                timed=row.timed,
                words=[schemas.RecordedWord.model_validate(word) for word in row.words],
            )
            for row in rows
        ]
    )


@router.get("/v1/lines/{name}")
async def line_audio(name: str, session: Session) -> Response:
    """A recorded line's MP3, by the id it is kept under, for any page; it never changes."""
    id_ = name.removesuffix(".mp3")
    row = await lines.get_line(session, id_)
    return Response(row.audio, media_type=MP3, headers={"Cache-Control": FOREVER})


@router.put("/v1/agents/{slug}/public/{name}")
async def publish_document(
    slug: KnownAgent, name: str, actor: PublishingKey, request: Request, session: Session
) -> dict[str, Any]:
    """Publish a JSON object under a name for any page to read, over the one before it."""
    raw = await capped_body(request, documents.LARGEST, "a published document")
    try:
        body: object = json.loads(raw)
    except ValueError as bad:
        raise ValidationError(NOT_AN_OBJECT) from bad
    if not isinstance(body, dict):
        raise ValidationError(NOT_AN_OBJECT)
    row = await documents.publish_document(
        session, org=actor.org, env=actor.env, agent=slug, name=name, body=cast("dict[str, Any]", body)
    )
    return row.body


# No key: the agent's org is the one its log belongs to; another env or a slug nobody holds is 404.
@router.get("/v1/agents/{slug}/public/{name}")
async def read_document(
    slug: str, name: str, request: Request, session: Session, env: Annotated[Env, Query()] = Env.production
) -> Response:
    """A document the agent's app published, for any page, with no key."""
    org = await registry_of(request).logs.store.owner(slug)
    if org is None:
        raise NotFound(NO_SUCH_AGENT.format(slug=slug))
    row = await documents.get_document(session, org=org, env=env, agent=slug, name=name)
    return Response(json.dumps(row.body), media_type="application/json", headers={"Cache-Control": A_MINUTE})
