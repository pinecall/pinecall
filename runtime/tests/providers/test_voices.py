"""A voice sample says the line, or the vendor's refusal of the voice as the settings refuse it."""

from tests.conftest import Gateway, Tenant, needs_the_services
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
