"""The clip a worker plays while a tool runs: the runtime's melody, none, or the org's own fetched once per box."""

import hashlib

import httpx

from runtime.actor import Scope
from runtime.enums import Env, HoldPlayed
from runtime.jobs.service.client import GatewayClient
from runtime.jobs.service.hold_clip import HOLD_CACHE, find_hold_clip
from runtime.session.service import runtime_melody
from runtime.wire.worker import HoldAudio

SCOPE = Scope("org_test", Env.sandbox, "")


def a_gateway(asked: list[str], clip: bytes = b"") -> GatewayClient:
    """A gateway that serves this clip and keeps the paths it was asked."""

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(200, content=clip)

    return GatewayClient(httpx.AsyncClient(transport=httpx.MockTransport(answer), base_url="http://gw"))


async def test_the_runtimes_melody_is_livekits_clip_on_this_disk_and_silence_plays_none() -> None:
    asked: list[str] = []
    melody = await find_hold_clip(a_gateway(asked), "front-desk", SCOPE, HoldAudio(played=HoldPlayed.default))
    silence = await find_hold_clip(a_gateway(asked), "front-desk", SCOPE, HoldAudio(played=HoldPlayed.off))
    assert melody is not None and melody == runtime_melody() and melody.is_file()
    assert silence is None
    assert asked == []


async def test_an_orgs_own_clip_is_fetched_once_and_read_from_the_boxs_cache_after() -> None:
    clip = b"OggS an org's own clip " + bytes(range(8))
    sha256 = hashlib.sha256(clip).hexdigest()
    (HOLD_CACHE / f"{sha256}.ogg").unlink(missing_ok=True)
    asked: list[str] = []
    held = HoldAudio(played=HoldPlayed.custom, sha256=sha256)
    first = await find_hold_clip(a_gateway(asked, clip), "front-desk", SCOPE, held)
    again = await find_hold_clip(a_gateway(asked, clip), "front-desk", SCOPE, held)
    assert first == again == HOLD_CACHE / f"{sha256}.ogg"
    assert first is not None and first.read_bytes() == clip
    assert len(asked) == 1


async def test_a_clip_that_cannot_be_fetched_plays_none() -> None:
    def away(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="away")

    gateway = GatewayClient(httpx.AsyncClient(transport=httpx.MockTransport(away), base_url="http://gw"))
    held = HoldAudio(played=HoldPlayed.custom, sha256="0" * 64)
    (HOLD_CACHE / f"{'0' * 64}.ogg").unlink(missing_ok=True)
    assert await find_hold_clip(gateway, "front-desk", SCOPE, held) is None
