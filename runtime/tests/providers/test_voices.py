"""A voice sample says the line, or the vendor's refusal of the voice as the settings refuse it."""

import pytest

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers.schemas import KeptVoice
from pinecall_runtime.providers.service import voices
from pinecall_runtime.providers.service.plugins import Running
from pinecall_runtime.providers.service.voices import ListedVoice, check_listed, check_narrowable
from tests.conftest import Gateway, Tenant, configured, needs_the_services
from tests.fakes import acme


@needs_the_services
async def test_a_voice_the_vendor_has_not_is_refused_in_one_sentence_never_a_502(
    gateway: Gateway, tenant: Tenant
) -> None:
    """A typo in the voice is the request's fault: 400, in the vendor's words."""
    asked = {"tts": acme.ACME, "voice": acme.UNKNOWN, "text": "hola"}
    refused = await gateway.http.post("/v1/voices/sample", json=asked, headers=tenant.person)
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"] == f"{acme.ACME} refused the voice: no such voice"


@needs_the_services
async def test_a_voice_the_vendor_has_answers_the_wav(gateway: Gateway, tenant: Tenant) -> None:
    """The line said, as WAV, with how long it took."""
    said = await gateway.http.post(
        "/v1/voices/sample", json={"tts": acme.ACME, "voice": "acme-ana", "text": "hola"}, headers=tenant.person
    )
    assert said.status_code == 200, said.text
    assert said.headers["content-type"] == "audio/wav"
    assert said.content[:4] == b"RIFF"


# L B4 (2026-10-23): ElevenLabs' plugin lists 150 voices with no language, and `--language en` passed every
# one of them through.
def test_a_language_cannot_narrow_a_listing_that_carries_none_and_is_refused_saying_so() -> None:
    bare = [ListedVoice(id="v1", name="Agus", detail={"category": "premade"})]
    with pytest.raises(ValidationError, match="elevenlabs lists its voices with no language, so --language en"):
        check_narrowable("elevenlabs", bare, "en")
    check_narrowable("elevenlabs", bare, None)
    check_narrowable("elevenlabs", [], "en")
    check_narrowable("cartesia", [ListedVoice(id="v2", name="Iria", detail={"language": "es"})], "en")


# Google's Gemini voices speak any name they are given, so `agent set --voice zzz` was kept (2026-10-25):
# the lists decide, the row's first, then the vendor's own, cloned voices among them.
async def test_a_voice_neither_the_row_nor_the_vendor_lists_is_refused_naming_the_list() -> None:
    row = configured().model_copy(update={"listed": {f"{acme.ACME}/es": (KeptVoice(id="acme-row", name="Rosa"),)}})
    own = {"voices": [{"id": "acme-cloned", "name": "Mine"}]}
    for kept in ("acme-row", "Rosa", "acme-cloned", "Mine"):
        await check_listed(Running(vendor=acme.ACME, credentials="k", voice=kept, options=own), row)
    with pytest.raises(ValidationError, match="it has no voice called zzz: `pinecall voices list --tts acme`"):
        await check_listed(Running(vendor=acme.ACME, credentials="k", voice="zzz", options=own), row)


async def test_a_vendor_that_lists_none_has_the_rows_voices_alone_and_with_none_there_is_left_to_its_trial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def lists_none(running: Running) -> list[ListedVoice]:
        raise voices.NotListed(running.vendor)

    monkeypatch.setattr(voices, "listed_by_vendor", lists_none)
    row = configured().model_copy(update={"listed": {f"{acme.ACME}/es": (KeptVoice(id="acme-row", name="Rosa"),)}})
    with pytest.raises(ValidationError, match="no voice called zzz"):
        await check_listed(Running(vendor=acme.ACME, credentials="k", voice="zzz"), row)
    await check_listed(Running(vendor=acme.ACME, credentials="k", voice="zzz"), configured())
