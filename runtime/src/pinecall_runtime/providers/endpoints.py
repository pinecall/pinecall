"""The providers endpoints: the catalogue, the org's and the box's vendor keys, voices, a sample."""

import dataclasses
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.accounts.service.attempts import AttemptThrottle
from pinecall_runtime.agents.declaration import Voice
from pinecall_runtime.agents.service import tuning
from pinecall_runtime.exceptions import NotFound, TooManyRequests, ValidationError
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.providers.auth import PipelineKey, ProvidersKey, TheOperator
from pinecall_runtime.providers.schemas import (
    Catalog,
    Catalogue,
    ListedVoice,
    ProviderKeyRequest,
    VendorsResponse,
    VoiceSampleRequest,
    VoicesListed,
)
from pinecall_runtime.providers.service import catalog, keyring, plugins, stages, trials, voices

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


# Built as a call builds the stage: the operator's options, on the key a call would use.
@router.get("/v1/voices")
async def list_voices(
    actor: PipelineKey,
    request: Request,
    session: Session,
    tts: Annotated[str, Query(min_length=1)],
    language: Annotated[str | None, Query()] = None,
) -> VoicesListed:
    """The voices the providers row lists for a vendor, else its plugin's; neither is a 404."""
    configured = await catalog.get_catalog(session)
    named = plugins.installed_vendor(tts)
    spoken = plugins.primary_language(language)
    listed = voices.listed_in_catalog(configured, named, spoken)
    # The row lists this vendor's voices by language: one it lists none in is said as that.
    if not listed and spoken is not None and voices.listed_in_catalog(configured, named, None):
        raise NotFound(f"{named} lists no voice in {language}: drop --language to see every one")
    if not listed and not keyring.lists_voices(named, ("tts",)):
        raise voices.NotListed(named)
    if not listed:
        keys = await keyring.keys_of(session, _vault(request), actor.scope)
        stage = keyring.stage_on_its_key("tts", Voice(provider=named), configured, keys)
        listed = await voices.listed_by_vendor(dataclasses.replace(stage, language=spoken))
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
    default = configured.defaults["tts"].vendor
    named = tuning.model_named(body.tts, "tts", in_use=default)
    voice = Voice(
        provider=default if named is None else named.provider,
        model=body.model or (None if named is None else named.model or None),
        voice_id=body.voice,
    )
    keys = await keyring.keys_of(session, _vault(request), actor.scope)
    stage = keyring.stage_on_its_key("tts", voice, configured, keys)
    heard = await voices.sample(dataclasses.replace(stage, voice=voice.voice_id, language=language), text)
    timing = f"first-audio;dur={heard.first_audio_ms}, total;dur={heard.total_ms}"
    return Response(content=heard.wav, media_type=WAV, headers={"Server-Timing": timing})


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
    )
