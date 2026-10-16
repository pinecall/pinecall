"""The agents endpoints: the org's held agents, what a worker asks about one, its pipeline, melody and widget."""

import asyncio
import dataclasses
import time
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from pinecall_runtime.agents import schemas
from pinecall_runtime.agents.auth import (
    CallsKey,
    DeclarationKey,
    PipelineKey,
    TalkKey,
    WorkerKey,
    sees_every_scope,
)
from pinecall_runtime.agents.declaration import AgentConfig, Greeting, Modality
from pinecall_runtime.agents.service import hold_audio, settings, widgets
from pinecall_runtime.agents.service.registry import AgentRegistry, Registration, named_holder
from pinecall_runtime.agents.service.settings import Picked
from pinecall_runtime.agents.service.widgets import Clip, Look
from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import Channel, HoldPlayed, KeyScope
from pinecall_runtime.exceptions import NotFound, PinecallError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.kit.http import capped_body
from pinecall_runtime.postgres import Session
from pinecall_runtime.providers import service as providers
from pinecall_runtime.providers.schemas import Catalog
from pinecall_runtime.wire.parts import GreetingConfig

router = APIRouter()

# Every agent answers on the widget; no route row is needed for it.
ON_THE_WEB: frozenset[Channel] = frozenset({Channel.web})
# Medians pool the turns of this many calls, so a short call weighs as much as its turns.
LAST_CALLS = 20
# The whole file in one request; a five-minute mp3 is under 10 MB.
LONGEST_UPLOAD = 20 * 1024 * 1024
OGG = "audio/ogg"


# ── what a worker asks ──


# A worker names the call it asks for before opening it (`for_call`: `call` would ask to act in an
# opened call's scope), so a canary's share is picked by the call's id; a worker that names none
# (an older one) is answered the version every call off the canary runs.
@router.get("/v1/agents/{slug}/config")
async def agent_config(
    slug: str,
    actor: DeclarationKey,
    request: Request,
    session: Session,
    for_call: Annotated[str | None, Query()] = None,
) -> AgentConfig:
    """The agent as the scope runs it, for the call named: its declaration under the settings."""
    found = _registration_of(request, actor.scope, slug)
    catalog = await providers.get_catalog(session)
    tuned, _ = await settings.tuned_for_call(session, found.config, actor.scope, catalog, Picked(call=for_call))
    return tuned


# The one answer that carries keys: to the fleet's key, or the org's own worker's. The box's
# keys leave it only for its own workers: an org's process is handed the org's keys alone.
@router.get("/v1/agents/{slug}/provider-keys")
async def agent_credentials(
    slug: str, actor: WorkerKey, request: Request, session: Session, for_call: Annotated[str | None, Query()] = None
) -> schemas.PipelineKeys:
    """The three stages a call of the agent runs, each on its key, and the org's collector."""
    found = _registration_of(request, actor.scope, slug)
    catalog = await providers.get_catalog(session)
    tuned, _ = await settings.tuned_for_call(session, found.config, actor.scope, catalog, Picked(call=for_call))
    keys = await providers.keys_of(session, _vault(request), actor.scope)
    if KeyScope.fleet not in actor.scopes:
        keys = dataclasses.replace(keys, lends=frozenset())
    counters: calls.VendorCounters = request.app.state.counters
    at = time.monotonic()
    stages = providers.build_pipeline(tuned, catalog, keys).demoting(counters.failing(at))
    counters.handed_out((stages.llm.vendor, stages.stt.vendor, stages.tts.vendor), at)
    traced = await compliance.telemetry_of(session, _vault(request), actor.org)
    return schemas.PipelineKeys(
        llm=_running_stage(stages.llm),
        stt=_running_stage(stages.stt),
        tts=_running_stage(stages.tts),
        telemetry=None
        if traced is None
        else schemas.TelemetryTarget(endpoint=traced.endpoint, headers=dict(traced.headers), pii=traced.pii),
    )


@router.get("/v1/agents/{slug}/hold-audio")
async def worker_hold_audio(slug: str, actor: WorkerKey, session: Session) -> schemas.HoldAudio:
    """What a caller of the agent hears while a tool runs."""
    return schemas.HoldAudio.of(await widgets.get_hold_audio(session, actor.org, actor.env, slug))


@router.get("/v1/agents/{slug}/hold-audio/audio")
async def worker_hold_clip(slug: str, actor: WorkerKey, session: Session) -> Response:
    """The org's own clip, Ogg Opus."""
    audio = await widgets.get_hold_clip(session, actor.org, actor.env, slug)
    if audio is None:
        raise NotFound(f"agent {slug} plays no clip of its own")
    return Response(audio, media_type=OGG)


# ── the org's agents ──


@router.get("/v1/agents")
async def list_agents(actor: CallsKey, request: Request, session: Session) -> schemas.AgentList:
    """The org's held agents in the env: one row per slug, one per scope for a team reader."""
    answering: dict[str, set[Channel]] = {}
    for route in await channels.routes_of_org(session, actor.org, actor.env):
        answering.setdefault(route.agent, set()).add(route.channel)
    listed: list[schemas.AgentRow] = []
    for registration in _registry(request).holding(actor.scope, every_scope=sees_every_scope(actor)):
        listed.append(
            schemas.AgentRow(
                slug=registration.slug,
                channels=sorted(answering.get(registration.slug, set()) | ON_THE_WEB),
                holder=await named_holder(session, registration.scope),
            )
        )
    return schemas.AgentList(agents=listed)


# ── the pipeline, as the next call would be built ──


# Nothing is built: a vendor without a key is a reason, not a failure.
@router.get("/v1/agents/{slug}/pipeline")
async def pipeline_report(slug: str, actor: PipelineKey, request: Request, session: Session) -> schemas.PipelineReport:
    """The agent's three stages, the catalogue, and the latencies of its last calls."""
    registration = _registry(request).holder_of(actor.scope, slug)
    declared = AgentConfig(slug=slug) if registration is None else registration.config
    catalog = await providers.get_catalog(session)
    config, _ = await settings.tuned_for_call(session, declared, actor.scope, catalog)
    keys = await providers.keys_of(session, _vault(request), actor.scope)
    language = providers.primary_language(config.language)
    stages = {
        "hears": _stage("stt", config, catalog, language=language),
        "decides": _stage("llm", config, catalog, language=None),
        "speaks": _stage("tts", config, catalog, language=language),
    }
    listed = providers.catalogue_of(catalog, keys)
    counted, medians = await calls.recent_latencies(session, request.app.state.logs, slug, LAST_CALLS)
    return schemas.PipelineReport(
        agent=slug,
        hears=stages["hears"],
        decides=stages["decides"],
        speaks=stages["speaks"],
        greeting=_greeting(config.greeting),
        voices=listed.voices,
        providers=listed.providers,
        defaults=listed.defaults,
        models=listed.models,
        calls=counted,
        medians=[schemas.Measured(name=row.name, seconds=row.seconds, turns=row.turns) for row in medians],
        unavailable_reasons=_unavailable(stages, keys),
    )


# The melody and the widget are the agent's in an env, whoever holds it.
@router.get("/v1/agents/{slug}/pipeline/hold-audio")
async def hold_audio_of(slug: str, actor: PipelineKey, session: Session) -> schemas.HoldAudio:
    """What the agent plays while a tool runs: the box's melody, silence, or a clip of its own."""
    return schemas.HoldAudio.of(await widgets.get_hold_audio(session, actor.org, actor.env, slug))


# The body is the file, no multipart; the name rides the query. Converted here, once, so no
# worker decodes a tenant's upload in the middle of a call.
@router.put("/v1/agents/{slug}/pipeline/hold-audio")
async def upload_hold_audio(
    slug: str,
    request: Request,
    actor: PipelineKey,
    session: Session,
    name: Annotated[str | None, Query(max_length=200)] = None,
) -> schemas.HoldAudio:
    """A file of the org's as the agent's melody, from the next call on."""
    data = await capped_body(request, LONGEST_UPLOAD, "a hold melody as uploaded")
    melody = await asyncio.to_thread(hold_audio.convert_upload, data)
    clip = Clip(audio=melody.audio, seconds=melody.seconds, name=(name or "").strip() or "melody")
    return schemas.HoldAudio.of(await widgets.keep_hold_clip(session, actor.org, actor.env, slug, clip))


@router.get("/v1/agents/{slug}/pipeline/hold-audio/audio")
async def hold_audio_clip(slug: str, actor: PipelineKey, session: Session) -> Response:
    """The agent's own clip, Ogg Opus, to hear before a caller does."""
    audio = await widgets.get_hold_clip(session, actor.org, actor.env, slug)
    if audio is None:
        raise NotFound(f"agent {slug} plays no clip of its own: the box's melody is the worker's, off or default")
    return Response(audio, media_type=OGG)


@router.put("/v1/agents/{slug}/pipeline/hold-audio/played")
async def choose_hold_audio(
    slug: str, body: schemas.PlayedRequest, actor: PipelineKey, session: Session
) -> schemas.HoldAudio:
    """The box's melody back, or silence; an uploaded clip is forgotten either way."""
    if body.played == "default":
        await widgets.forget_hold(session, actor.org, actor.env, slug)
        return schemas.HoldAudio(played="default")
    await widgets.silence_hold(session, actor.org, actor.env, slug)
    return schemas.HoldAudio(played=HoldPlayed.off)


# ── the widget ──


# `talk`: whoever may mint the widget's token may read how it looks.
@router.get("/v1/agents/{slug}/widget")
async def get_widget(slug: str, actor: TalkKey, session: Session) -> schemas.WidgetSettings:
    """How the agent's widget looks in the key's env; the widget's own defaults when unset."""
    return _widget_row(await widgets.get_look(session, actor.org, actor.env, slug))


# `pipeline`: the same key that sets the agent's greeting and voice.
@router.put("/v1/agents/{slug}/widget")
async def put_widget(
    slug: str, body: schemas.WidgetSettings, actor: PipelineKey, session: Session
) -> schemas.WidgetSettings:
    """Replace how the widget looks, whole; a null field is the widget's own default."""
    look = Look(
        title=body.title,
        tagline=body.tagline,
        greeting=body.greeting,
        accent=body.accent,
        autostart=body.autostart,
        theme=body.theme,
    )
    await widgets.put_look(session, actor.org, actor.env, slug, look)
    return _widget_row(look)


# ── private ──


def _registry(request: Request) -> AgentRegistry:
    registry: AgentRegistry = request.app.state.registry
    return registry


def _vault(request: Request) -> Vault:
    vault: Vault = handles_of(request).vault
    return vault


# Another org's agent is the same 404 as nobody's: its existence does not leak.
def _registration_of(request: Request, scope: Scope, slug: str) -> Registration:
    registration = _registry(request).holder_of(scope, slug)
    if registration is None or registration.scope.org != scope.org:
        raise NotFound(f"no app holds agent {slug}: start one, or deploy it")
    return registration


def _running_stage(running: providers.Running) -> schemas.RunningStage:
    return schemas.RunningStage(
        vendor=running.vendor,
        credentials=running.credentials if isinstance(running.credentials, str) else dict(running.credentials),
        model=running.model,
        builds=running.builds,
        options=dict(running.options),
        voice=running.voice,
        language=running.language,
        hints=list(running.hints),
        ends_the_turn=running.ends_the_turn,
        turn_model=running.turn_model,
        request=dict(running.request),
        lent=running.lent,
        fallbacks=[_running_stage(fallback) for fallback in running.fallbacks],
    )


def _widget_row(look: Look) -> schemas.WidgetSettings:
    return schemas.WidgetSettings(
        title=look.title,
        tagline=look.tagline,
        greeting=look.greeting,
        accent=look.accent,
        autostart=look.autostart,
        theme=look.theme,
    )


def _stage(modality: Modality, config: AgentConfig, catalog: Catalog, *, language: str | None) -> schemas.PipelineStage:
    default = catalog.defaults[modality]
    if modality == "tts":
        voice = config.voice
        return schemas.PipelineStage(
            vendor=default.vendor if voice is None else voice.provider,
            model=None if voice is None else voice.model,
            voice_id=None if voice is None else voice.voice_id,
            language=language,
        )
    declared = config.stt if modality == "stt" else config.llm
    return schemas.PipelineStage(
        vendor=default.vendor if declared is None else declared.provider,
        model=None if declared is None else declared.model or None,
        language=language,
    )


def _greeting(greeting: Greeting | None) -> GreetingConfig | None:
    if greeting is None:
        return None
    return GreetingConfig(say=greeting.say, reply=greeting.reply, allow_interruptions=greeting.allow_interruptions)


# Which stage has no key to run on, and why, before a call fails for want of it.
def _unavailable(stages: dict[str, schemas.PipelineStage], keys: providers.Keyring) -> dict[str, str]:
    missing: dict[str, str] = {}
    for where, stage in stages.items():
        try:
            providers.running_on(keys, stage.vendor, stage.model)
        except PinecallError as refused:
            missing[where] = str(refused)
    return missing
