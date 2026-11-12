"""A voice note is said back as text by the ears a call hears with, on the org's keys."""

import json

from websockets.exceptions import ConnectionClosed

from tests.conftest import Gateway, Tenant, needs_the_services
from tests.fakes import acme

PCM = "audio/L16; rate=16000; channels=1"
# Half a second of silence: acme's ears hear anything and say what they were built to.
NOTE = bytes(16000)


def _server(tenant: Tenant) -> dict[str, str]:
    return {"authorization": f"Bearer {tenant.server_key}"}


@needs_the_services
async def test_a_note_is_heard_by_the_boxs_default_ears(gateway: Gateway, tenant: Tenant) -> None:
    """No vendor named: the box's default STT, its answer and the audio's length."""
    heard = await gateway.http.post(
        "/v1/transcriptions?language=es", content=NOTE, headers={**_server(tenant), "content-type": PCM}
    )
    assert heard.status_code == 200, heard.text
    answer = heard.json()
    assert answer["vendor"] == acme.ACME
    assert answer["audio_ms"] == 500
    assert isinstance(answer["text"], str)


@needs_the_services
async def test_a_vendor_that_is_not_installed_is_the_requests_fault(gateway: Gateway, tenant: Tenant) -> None:
    refused = await gateway.http.post(
        "/v1/transcriptions?stt=nobody", content=NOTE, headers={**_server(tenant), "content-type": PCM}
    )
    assert refused.status_code == 400, refused.text
    assert "no vendor named 'nobody'" in refused.json()["detail"]


@needs_the_services
async def test_an_empty_body_is_the_requests_fault(gateway: Gateway, tenant: Tenant) -> None:
    refused = await gateway.http.post(
        "/v1/transcriptions", content=b"", headers={**_server(tenant), "content-type": PCM}
    )
    assert refused.status_code == 400, refused.text


@needs_the_services
async def test_a_dictation_is_heard_as_it_is_spoken_and_settles_with_done(gateway: Gateway, tenant: Tenant) -> None:
    """The org's key mints the token; the socket takes PCM, `end` closes the audio, `done` follows."""
    minted = await gateway.http.post(
        "/v1/transcriptions/token?language=es&hear=Brisa&hear=M%C3%A9dano", headers=_server(tenant)
    )
    assert minted.status_code == 200, minted.text
    body = minted.json()
    assert body["vendor"] == acme.ACME
    assert body["expires_in"] == 60
    async with gateway.socket(body["path"], {}) as socket:
        await socket.send(NOTE)
        await socket.send("end")
        kinds = [json.loads(message)["type"] async for message in socket]
    assert kinds[-1] == "done"


@needs_the_services
async def test_a_dictation_without_a_token_of_ours_is_refused(gateway: Gateway, tenant: Tenant) -> None:
    async with gateway.socket("/v1/transcriptions/stream?token=nonsense", {}) as socket:
        try:
            await socket.recv()
        except ConnectionClosed as closed:
            assert closed.rcvd is not None
            assert closed.rcvd.code == 4401
        else:
            raise AssertionError("a socket with no dictation token of ours was not closed")
