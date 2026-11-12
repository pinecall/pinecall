"""A call's recording once its session closed it: sealed under the call's key, kept on the disk or moved to a bucket."""

import base64
import logging
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest

from runtime.calls.recordings import SEALED_FILE, Bucket, Disk, Recordings, recording_path
from runtime.jobs.service.call_client import CallClient
from runtime.jobs.service.client import GatewayClient
from runtime.jobs.service.recordings import has_audio, keep_recording
from runtime.kit.sealed_file import ByteRange, new_key, on_disk, open_range, plain_size_of
from tests.fakes import bucket

AUDIO = b"OggS a call"

KEY = new_key()


def test_a_call_that_ended_before_its_session_recorded_has_no_file(tmp_path: Path) -> None:
    audio = recording_path(tmp_path, "call_1")
    assert not has_audio(audio)
    audio.write_bytes(b"")
    assert not has_audio(audio)
    audio.write_bytes(AUDIO)
    assert has_audio(audio)


def the_call_on(answers: list[HTTPStatus]) -> CallClient:
    """The call CA_1 at a gateway whose key door answers these, in order: the key, or a refusal."""

    def answer(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("POST", "/v1/calls/CA_1/recording/key")
        status = answers.pop(0)
        if status != HTTPStatus.OK:
            return httpx.Response(status, json={"detail": "no"})
        return httpx.Response(status, json={"key": base64.urlsafe_b64encode(KEY).decode()})

    http = httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(answer))
    return CallClient(GatewayClient(http), "CA_1")


def in_a_bucket(root: Path, remote: bucket.Bucket) -> Bucket:
    """The box's recordings in this bucket, the disk holding each until it is uploaded."""
    return Bucket(root, remote.name, remote.store_on(httpx.AsyncClient(transport=remote.transport())))


async def opened_whole(path: Path) -> bytes:
    sealed = await on_disk("CA_1", path)
    assert sealed is not None
    span = ByteRange(0, plain_size_of(sealed.size) - 1)
    return b"".join([piece async for piece in open_range(sealed, KEY, span)])


async def recorded(store: Recordings, root: Path, answers: list[HTTPStatus], within_s: float = 0.0) -> str | None:
    audio = recording_path(root, "CA_1")
    audio.write_bytes(AUDIO)
    return await keep_recording(store, the_call_on(answers), "org_1", audio, key_within_s=within_s)


async def test_a_written_recording_is_sealed_under_the_calls_key_and_moves_to_the_bucket(tmp_path: Path) -> None:
    remote = bucket.Bucket()
    kept = await recorded(in_a_bucket(tmp_path, remote), tmp_path, [HTTPStatus.OK])
    assert kept == str(recording_path(tmp_path, "CA_1").with_name(SEALED_FILE))
    assert list(remote.objects) == ["org_1/CA_1/audio.sealed"]
    assert AUDIO not in remote.objects["org_1/CA_1/audio.sealed"]
    tmp_path.joinpath("opened.sealed").write_bytes(remote.objects["org_1/CA_1/audio.sealed"])
    assert await opened_whole(tmp_path / "opened.sealed") == AUDIO


async def test_a_box_without_a_bucket_keeps_the_sealed_recording_where_it_was_written(tmp_path: Path) -> None:
    kept = await recorded(Disk(tmp_path), tmp_path, [HTTPStatus.OK])
    assert kept is not None and Path(kept).exists()
    assert not (tmp_path / "CA_1" / "audio.ogg").exists()
    assert await opened_whole(Path(kept)) == AUDIO


# Never kept as it was written: a gateway that refuses the key, or stays away past every wait,
# and the recording is removed, nothing reaches the bucket, and the seal names none.
@pytest.mark.parametrize("status", [HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT, HTTPStatus.BAD_GATEWAY])
async def test_a_recording_with_no_key_is_dropped_and_never_stored_plain(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, status: HTTPStatus
) -> None:
    remote = bucket.Bucket()
    with caplog.at_level(logging.WARNING):
        kept = await recorded(in_a_bucket(tmp_path, remote), tmp_path, [status])
    audio = tmp_path / "CA_1" / "audio.ogg"
    assert kept is None
    assert (remote.asked, audio.exists(), audio.with_name(SEALED_FILE).exists()) == ([], False, False)
    assert "the recording of CA_1 is dropped, never kept unsealed" in caplog.text


# A gateway away for a moment is asked again: the second answer seals the recording.
async def test_a_gateway_away_for_a_moment_is_asked_again_for_the_key(tmp_path: Path) -> None:
    answers = [HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.OK]
    kept = await recorded(Disk(tmp_path), tmp_path, answers, within_s=13.0)
    assert kept is not None and answers == []
    assert await opened_whole(Path(kept)) == AUDIO


async def test_a_bucket_that_refuses_leaves_the_recording_on_the_disk_and_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    remote = bucket.Bucket(refusal=503)
    with caplog.at_level(logging.WARNING):
        kept = await recorded(in_a_bucket(tmp_path, remote), tmp_path, [HTTPStatus.OK])
    assert kept is not None
    assert await opened_whole(Path(kept)) == AUDIO
    assert "the recording of CA_1 stays on this disk" in caplog.text
