"""The providers endpoints: the catalogue, the org's and the box's vendor keys, voices, a sample."""

import contextlib
import dataclasses
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, WebSocket, WebSocketDisconnect

from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.accounts.service.attempts import AttemptThrottle
from pinecall_runtime.agents.declaration import Model, Voice
from pinecall_runtime.exceptions import (
    NotFound,
    PayloadTooLarge,
    PinecallError,
    ServiceUnavailable,
    TooManyRequests,
    Unauthorized,
    ValidationError,
)
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import Handles, handles_of
from pinecall_runtime.kit.websockets import close_reason, code_of, refuse_socket
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.providers.auth import EarsKey, PipelineKey, ProvidersKey, TheOperator
from pinecall_runtime.providers.schemas import (
    Advice,
    AdvisedStage,
    Catalog,
    Catalogue,
    DictationTokenResponse,
    ListedVoice,
    ProviderKeyRequest,
    Stage,
    TranscriptionResponse,
    VendorsResponse,
    VoiceSampleRequest,
    VoicesListed,
)
from pinecall_runtime.providers.service import (
    advice,
    catalog,
    keyring,
    machine,
    notes,
    plugins,
    published,
    stages,
    trials,
    voices,
)

router = APIRouter()

WAV = "audio/wav"
# Long enough for a greeting, short enough to keep the vendor's cost to seconds.
LONGEST_SAMPLE = 400
# What a voice says when the picker names no line and the providers row has none in the language.
A_LINE = "Hello, this is the voice you are listening to."
# The account the box buys numbers on is sealed beside the keys and is no vendor of a call.
NUMBERS_ACCOUNT = "twilio"


# ── an org's ──


# The same for every key of an org: what is installed, and whose key would run each vendor.
@router.get("/v1/providers")
async def catalogue(actor: ProvidersKey, request: Request, session: Session) -> Catalogue:
    """Every vendor this build runs and how this org may run it, the defaults, the models named."""
    configured = await catalog.get_catalog(session)
    keys = await keyring.keys_of(session, _vault(request), actor.scope)
    return keyring.catalogue_of(configured, keys)


# Vendor names only, never a key or a prefix of one.
@router.get("/v1/provider-keys")
async def own_vendors(actor: ProvidersKey, session: Session) -> VendorsResponse:
    """The vendors the org brought its own credentials for."""
    return VendorsResponse(vendors=await keyring.own_vendors(session, actor.org))


@router.put("/v1/provider-keys/{vendor}", status_code=204)
async def bring_key(
    vendor: str, body: ProviderKeyRequest, actor: ProvidersKey, request: Request, session: Session
) -> None:
    """Keep the org's own credentials for a vendor; its calls run on them from the next one."""
    named = plugins.installed_vendor(vendor)
    credentials = keyring.credentials_from(body)
    stages.check_credentials(named, credentials)
    await trials.try_key(plugins.installed()[named], credentials, await catalog.get_catalog(session))
    await keyring.put_own_credentials(session, _vault(request), actor.org, named, credentials)


@router.delete("/v1/provider-keys/{vendor}", status_code=204)
async def take_key_back(vendor: str, actor: ProvidersKey, session: Session) -> None:
    """Forget the org's credentials for a vendor; its calls run on the box's from the next one."""
    named = plugins.installed_vendor(vendor)
    if not await keyring.drop_own_credentials(session, actor.org, named):
        raise NotFound(f"this org brought no key for {named}")


# `pinecall login` asks this once signed in: the host advises from what it serves and lends, and the
# org's own keys. The machine is its operator's to see, and only where the row's open-model servers
# are on this same host.
@router.get("/v1/providers/advice")
async def advise(actor: ProvidersKey, request: Request, session: Session) -> Advice:
    """What this host advises the org to run, stage by stage, and whose key each runs on."""
    configured = await catalog.get_catalog(session)
    keys = await keyring.keys_of(session, _vault(request), actor.scope)
    served = await advice.served_by(configured)
    operator = actor.person is not None and actor.person.operator
    read = machine.recommendation() if operator and served.on_this_host else None
    return Advice(
        stages=[
            AdvisedStage(stage=one.stage, choice=one.choice, runs_on=one.runs_on, served=list(one.served))
            for one in advice.advise(configured, keys, served)
        ],
        lends=None if keys.lends is None else sorted(keys.lends),
        judge=_stage_name(configured.judge.llm) if configured.judge else None,
        caller=_stage_name(configured.caller.llm) if configured.caller and configured.caller.llm else None,
        machine=read,
    )


# Built as a call builds the stage: the operator's options, on the key a call would use.
@router.get("/v1/voices")
async def list_voices(
    actor: PipelineKey,
    request: Request,
    session: Session,
    tts: Annotated[str, Query(min_length=1)],
    language: Annotated[str | None, Query()] = None,
) -> VoicesListed:
    """The voices the providers row lists for a vendor, else its plugin's, else those voicedex knows it publishes;
    none is a 404. voicedex adds each voice's preview, gender and accent where the list lacks them."""
    configured = await catalog.get_catalog(session)
    named = plugins.installed_vendor(tts)
    spoken = plugins.primary_language(language)
    listed = voices.listed_in_catalog(configured, named, spoken)
    # The row lists this vendor's voices by language: one it lists none in is said as that.
    if not listed and spoken is not None and voices.listed_in_catalog(configured, named, None):
        raise NotFound(f"{named} lists no voice in {language}: drop --language to see every one")
    if not listed and keyring.lists_voices(named, ("tts",)):
        keys = await keyring.keys_of(session, _vault(request), actor.scope)
        stage = keyring.stage_on_its_key("tts", Voice(provider=named), configured, keys)
        listed = await voices.listed_by_vendor(dataclasses.replace(stage, language=spoken))
    if not listed:
        # The language as asked, so `es-AR` finds Argentine voices and `es` every Spanish one.
        listed = list(published.voices_of(named, language))
    if not listed:
        raise voices.NotListed(named)
    listed = published.described(named, listed)
    return VoicesListed(
        tts=tts,
        language=language,
        voices=[
            voice
            for item in listed
            if (voice := _listed_voice(item)) is not None
            and (spoken is None or not voice.language or voice.language.startswith(spoken))
        ],
    )


# The three words are read exactly as the settings endpoint reads them, so what plays is what saves.
# The answer is the WAV itself, its latencies in Server-Timing, which a browser shows.
@router.post("/v1/voices/sample")
async def voice_sample(body: VoiceSampleRequest, actor: PipelineKey, request: Request, session: Session) -> Response:
    """The line said by that vendor's voice, over the path a call speaks on."""
    throttle: AttemptThrottle = request.app.state.samples
    if not await throttle.is_allowed(actor.key_id):
        raise TooManyRequests(
            f"this key asked for its {throttle.tries} samples this minute: the ceiling is {throttle.tries} a minute",
            retry_after_s=60,
        )
    configured = await catalog.get_catalog(session)
    language = plugins.primary_language(body.language)
    text = body.text or configured.lines.get(language or "", A_LINE)
    if len(text) > LONGEST_SAMPLE:
        raise ValidationError(f"a sample says a sentence: {len(text)} characters, and the ceiling is {LONGEST_SAMPLE}")
    # `tts` names a vendor, never a model: a word that is no vendor is refused as one, not tried as a model.
    vendor = configured.defaults["tts"].vendor if not body.tts else plugins.vendor_doing(body.tts, "tts")
    voice = Voice(provider=vendor, model=body.model or None, voice_id=body.voice)
    keys = await keyring.keys_of(session, _vault(request), actor.scope)
    stage = keyring.stage_on_its_key("tts", voice, configured, keys)
    heard = await voices.sample(dataclasses.replace(stage, voice=voice.voice_id, language=language), text)
    timing = f"first-audio;dur={heard.first_audio_ms}, total;dur={heard.total_ms}"
    return Response(content=heard.wav, media_type=WAV, headers={"Server-Timing": timing})


# A voice note from a chat, said back as text by the ears a call hears with: the box's default
# vendor, or the one `stt` names (`model` too), on the org's own key or one the box lends. The body
# is the audio: raw PCM as a browser records it (`Content-Type: audio/L16; rate=16000; channels=1`),
# or a container (WAV, WebM, Ogg, MP4, MP3) decoded here. `language` is the note's, as a call's.
@router.post("/v1/transcriptions")
async def transcribe_note(
    actor: EarsKey,
    request: Request,
    session: Session,
    stt: str | None = None,
    model: str | None = None,
    language: str | None = None,
    hear: Annotated[list[str] | None, Query()] = None,
) -> TranscriptionResponse:
    """The note's words, heard on the keys the org's calls run on."""
    throttle: AttemptThrottle = request.app.state.transcriptions
    if not await throttle.is_allowed(actor.key_id):
        raise TooManyRequests(
            f"this key sent its {throttle.tries} notes this minute: the ceiling is {throttle.tries} a minute",
            retry_after_s=60,
        )
    audio = await request.body()
    if not audio:
        raise ValidationError("the body is the audio, and it is empty")
    if len(audio) > notes.LONGEST_NOTE:
        raise PayloadTooLarge(f"a note is at most {notes.LONGEST_NOTE // (1024 * 1024)} MB of audio")
    note = notes.note_of(audio, request.headers.get("content-type", ""))
    configured = await catalog.get_catalog(session)
    # `stt` names a vendor, never a model: a word that is no vendor is refused as one, not tried as a model.
    declared = None if not stt else Model(provider=plugins.vendor_doing(stt, "stt"), model=model or "")
    keys = await keyring.keys_of(session, _vault(request), actor.scope)
    stage = keyring.stage_on_its_key("stt", declared, configured, keys)
    heard = await notes.transcribe(
        dataclasses.replace(stage, language=plugins.primary_language(language)), note, notes.terms_of(hear)
    )
    return TranscriptionResponse(text=heard.text, language=heard.language, audio_ms=heard.audio_ms, vendor=stage.vendor)


# The words as they are spoken: a page asks its server for a token (the org's key mints it, the
# page never holds the key), then opens the socket with it and sends raw 16 kHz PCM as it records.
@router.post("/v1/transcriptions/token")
async def dictation_token(
    actor: EarsKey,
    request: Request,
    session: Session,
    stt: str | None = None,
    model: str | None = None,
    language: str | None = None,
    hear: Annotated[list[str] | None, Query()] = None,
) -> DictationTokenResponse:
    """A minute's token for one dictation on the org's keys, with the ears and language asked for."""
    throttle: AttemptThrottle = request.app.state.transcriptions
    if not await throttle.is_allowed(actor.key_id):
        raise TooManyRequests(
            f"this key asked for its {throttle.tries} dictations this minute: the ceiling is {throttle.tries} a minute",
            retry_after_s=60,
        )
    configured = await catalog.get_catalog(session)
    vendor = plugins.vendor_doing(stt, "stt") if stt else configured.defaults["stt"].vendor
    # Refused now, not when the page opens the socket: the ears must run on a key this org may use.
    keys = await keyring.keys_of(session, _vault(request), actor.scope)
    keyring.stage_on_its_key("stt", Model(provider=vendor, model=model or "") if stt else None, configured, keys)
    token = notes.dictation_token(
        _own_key(handles_of(request)),
        actor.scope,
        stt and vendor,
        model,
        plugins.primary_language(language),
        notes.terms_of(hear),
    )
    return DictationTokenResponse(
        token=token,
        path=f"/v1/transcriptions/stream?token={token}",
        expires_in=notes.DICTATION_TOKEN_TTL_S,
        vendor=vendor,
    )


@router.websocket("/v1/transcriptions/stream")
async def dictation(websocket: WebSocket, token: str = "") -> None:
    """Raw 16 kHz PCM frames in, `{type: interim|final, text}` out as it is heard; `end` closes the
    audio and `{type: done}` follows once the words are settled."""
    handles: Handles = websocket.app.state.handles
    try:
        asked = notes.dictation_of(_own_key(handles), token)
        if asked is None:
            raise Unauthorized("the token is no dictation token of this gateway's, or it expired: ask for a new one")
        async with handles.sessions.begin() as session:
            configured = await catalog.get_catalog(session)
            keys = await keyring.keys_of(session, handles.vault, asked.scope)
        declared = Model(provider=asked.stt, model=asked.model or "") if asked.stt else None
        stage = keyring.stage_on_its_key("stt", declared, configured, keys)
    except PinecallError as refused:
        await refuse_socket(websocket, refused)
        return
    await websocket.accept()

    async def heard() -> AsyncIterator[bytes | None]:
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("bytes"):
                    yield message["bytes"]
                elif message.get("text") == notes.END:
                    yield None
                    return
        except WebSocketDisconnect:
            return

    async def said(kind: str, text: str) -> None:
        await websocket.send_json({"type": kind, "text": text})

    try:
        await notes.dictate(dataclasses.replace(stage, language=asked.language), heard(), said, asked.hear)
        await websocket.close()
    except PinecallError as refused:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=code_of(refused), reason=close_reason(str(refused)))
    except (RuntimeError, WebSocketDisconnect):
        return


def _own_key(handles: Handles) -> str:
    if handles.settings.token_key is None:
        raise ServiceUnavailable("this gateway signs no tokens: PINECALL_TOKEN_KEY is unset")
    return handles.settings.token_key.get_secret_value()


# ── the box's ──


@router.get("/v1/ops/providers")
async def get_providers(_actor: TheOperator, session: Session) -> Catalog:
    """The providers row: defaults, models, voices, tuning, rates, the judge, the embedder."""
    return await catalog.get_catalog(session)


@router.put("/v1/ops/providers")
async def put_providers(body: Catalog, _actor: TheOperator, session: Session) -> Catalog:
    """The providers row replaced whole; a vendor not installed or not doing its stage refused."""
    await catalog.put_catalog(session, body)
    return body


# Offering a vendor is holding its key: the box's credentials, sealed, never read back.
@router.get("/v1/ops/provider-keys")
async def box_vendors(_actor: TheOperator, request: Request, session: Session) -> VendorsResponse:
    """The vendors the box holds a key for, never the key."""
    credentials = await keyring.box_credentials(session, _vault(request))
    return VendorsResponse(vendors=sorted(set(credentials) - {NUMBERS_ACCOUNT}))


@router.put("/v1/ops/provider-keys/{vendor}", status_code=204)
async def put_box_key(
    vendor: str, body: ProviderKeyRequest, _actor: TheOperator, request: Request, session: Session
) -> None:
    """The box's own credentials for a vendor; orgs it lends to run on them from the next call."""
    named, credentials = plugins.installed_vendor(vendor), keyring.credentials_from(body)
    await trials.try_key(plugins.installed()[named], credentials, await catalog.get_catalog(session))
    await keyring.put_box_credentials(session, _vault(request), named, credentials)


@router.delete("/v1/ops/provider-keys/{vendor}", status_code=204)
async def drop_box_key(vendor: str, _actor: TheOperator, session: Session) -> None:
    """The box stops offering the vendor on its key; 404 when it held none."""
    named = plugins.installed_vendor(vendor)
    if not await keyring.drop_box_credentials(session, named):
        raise NotFound(f"this box holds no key for {named}")


# ── an org's vendor keys, set for it by the operator ──


@router.get("/v1/ops/orgs/{named}/provider-keys")
async def org_vendors(named: str, _actor: TheOperator, session: Session) -> VendorsResponse:
    """The vendors the org brought its own credentials for, never the credentials."""
    with box_wide():
        org = await orgs.get_org(session, named)
        return VendorsResponse(vendors=await keyring.own_vendors(session, org.id))


@router.put("/v1/ops/orgs/{named}/provider-keys/{vendor}", status_code=204)
async def put_org_vendor_key(
    named: str, vendor: str, body: ProviderKeyRequest, _actor: TheOperator, request: Request, session: Session
) -> None:
    """The org's own credentials for a vendor, set for it; its calls run on them next."""
    named_vendor, credentials = plugins.installed_vendor(vendor), keyring.credentials_from(body)
    stages.check_credentials(named_vendor, credentials)
    await trials.try_key(plugins.installed()[named_vendor], credentials, await catalog.get_catalog(session))
    with box_wide():
        org = await orgs.get_org(session, named)
        await keyring.put_own_credentials(session, _vault(request), org.id, named_vendor, credentials)


@router.delete("/v1/ops/orgs/{named}/provider-keys/{vendor}", status_code=204)
async def drop_org_vendor_key(named: str, vendor: str, _actor: TheOperator, session: Session) -> None:
    """The org's credentials for a vendor taken back; its calls run on the box's next."""
    named_vendor = plugins.installed_vendor(vendor)
    with box_wide():
        org = await orgs.get_org(session, named)
        if not await keyring.drop_own_credentials(session, org.id, named_vendor):
            raise NotFound(f"org {org.slug} brought no key for {named_vendor}")


def _vault(request: Request) -> Vault:
    vault: Vault = handles_of(request).vault
    return vault


def _listed_voice(item: voices.ListedVoice) -> ListedVoice | None:
    detail = item.detail
    return ListedVoice(
        id=item.id,
        name=item.name,
        language=str(detail.get("language") or ""),
        description=str(detail.get("description") or ""),
        gender=str(detail.get("gender") or ""),
        country=str(detail.get("country") or ""),
        accent=str(detail.get("accent") or ""),
        preview_url=str(detail["preview_url"]) if detail.get("preview_url") else None,
    )


def _stage_name(stage: Stage) -> str:
    return f"{stage.vendor}/{stage.model}" if stage.model else stage.vendor
