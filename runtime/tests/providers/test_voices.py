"""A voice sample says the line, or the vendor's refusal of the voice as the settings refuse it; the
catalogue and the voices answer anyone, and a bare request never spends a key."""

from pinecall_runtime.jobs.service.client import GatewayClient
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


@needs_the_services
async def test_anyone_lists_the_vendors_and_the_models_with_no_org_counted(gateway: Gateway) -> None:
    """The catalogue answers a bare request; no org's key is counted, so no vendor reads as ready."""
    answer = await gateway.http.get("/v1/providers")
    assert answer.status_code == 200, answer.text
    listed = answer.json()
    assert any(row["name"] == acme.ACME for row in listed["providers"])
    assert not any(row["ready"] for row in listed["providers"])


@needs_the_services
async def test_a_bare_request_never_spends_a_key_on_a_vendors_list(gateway: Gateway) -> None:
    """acme's voices come from its plugin alone, on a key: a request that brings none is told there are none."""
    answer = await gateway.http.get("/v1/voices", params={"tts": acme.ACME})
    assert answer.status_code == 404, answer.text


@needs_the_services
async def test_a_key_that_opens_neither_scope_is_still_refused(fleet: GatewayClient) -> None:
    """Open to anyone is not open to any key: a fleet's key, which opens neither providers nor pipeline, is a 403."""
    answer = await fleet.http.get("/v1/providers")
    assert answer.status_code == 403, answer.text
