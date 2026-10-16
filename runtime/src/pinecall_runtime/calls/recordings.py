"""Where a call's audio is kept: the disk it was recorded on, or a bucket, under its org."""

import asyncio
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path, PurePath

import httpx

from pinecall_runtime.config import Settings
from pinecall_runtime.exceptions import UpstreamError, ValidationError
from pinecall_runtime.kit.s3 import ObjectStore
from pinecall_runtime.kit.sealed_audio import (
    HEADER,
    MAGIC,
    ByteRange,
    SealedObject,
    open_range,
    parse_range,
    recorded_size,
)

# The recorder's file in the call's own directory: `<root>/<call>/audio.ogg` on the disk,
# `<org>/<call>/audio.ogg` in the bucket. Sealed under the call's own key, it is `audio.sealed`
# beside it (kit/sealed_audio.py): the name says which a stored recording is.
AUDIO_FILE = "audio.ogg"
SEALED_FILE = "audio.sealed"
# Every object a call's recording may be kept as.
NAMES = (AUDIO_FILE, SEALED_FILE)

# An org's erasure deletes its calls' objects this many at a time.
DELETED_AT_ONCE = 16


@dataclass(frozen=True)
class Fetched:
    """A recording as a player reads it: the status and headers to pass on, and its bytes."""

    status: int
    headers: dict[str, str]
    body: AsyncIterator[bytes]


@dataclass(frozen=True)
class Disk:
    """Recordings kept on the disk they were recorded on: a box with no bucket, as always."""

    root: Path

    async def store(self, org: str, call: str, audio: Path) -> None:
        """Nothing to do: the recorder's file is where it is kept."""

    async def fetch(self, org: str, call: str, byte_range: str | None) -> Fetched | None:
        """None: the file on the disk is the recording, and the endpoint serves it as a file."""

    async def sealed(self, org: str, call: str) -> SealedObject | None:
        """None: a sealed file on the disk is read from where the call's summary says it is."""

    async def erase(self, _org: str, calls: list[str]) -> int:
        """Remove each call's recording directory; how many calls had one. The disk knows no org."""
        return len(await asyncio.to_thread(_removed, self.root, calls))


@dataclass(frozen=True)
class Bucket:
    """Recordings moved to a bucket of the object store once written, the disk holding one until."""

    root: Path
    name: str
    objects: ObjectStore

    async def store(self, org: str, call: str, audio: Path) -> None:
        """Upload the file under the org, then remove it from the disk; raise if it stayed."""
        kind = "audio/ogg" if audio.name == AUDIO_FILE else "application/octet-stream"
        body = await asyncio.to_thread(audio.read_bytes)
        await self.objects.put(self.name, _object_name(org, call, audio.name), body, kind)
        await asyncio.to_thread(_removed, self.root, [call])

    async def fetch(self, org: str, call: str, byte_range: str | None) -> Fetched | None:
        """The recording's bytes, the range asked for when one is; None while it is not there."""
        what = _object_name(org, call, AUDIO_FILE)
        size = await self.objects.head(self.name, what)
        if size is None:
            return None
        span = parse_range(byte_range, size)
        if span is not None and span.first >= size:
            return Fetched(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, {"content-range": f"bytes */{size}"}, _nothing())
        whole = span or ByteRange(0, size - 1)
        body = self.objects.read(self.name, what, offset=whole.first, length=whole.length) if size else _nothing()
        headers = {"accept-ranges": "bytes", "content-length": str(whole.length)}
        if span is None:
            return Fetched(HTTPStatus.OK, headers, body)
        return Fetched(
            HTTPStatus.PARTIAL_CONTENT, {**headers, "content-range": f"bytes {span.first}-{span.last}/{size}"}, body
        )

    async def sealed(self, org: str, call: str) -> SealedObject | None:
        """The call's sealed object, read by ranges; None while it is not in the bucket."""
        what = _object_name(org, call, SEALED_FILE)
        size = await self.objects.head(self.name, what)
        if size is None:
            return None
        header = b"".join([piece async for piece in self.objects.read(self.name, what, offset=0, length=HEADER)])
        if not header.startswith(MAGIC):
            raise UpstreamError(f"the sealed recording of {call} does not open: {what} is not a sealed recording")

        async def read(offset: int, length: int) -> AsyncIterator[bytes]:
            async for piece in self.objects.read(self.name, what, offset=offset, length=length):
                yield piece

        return SealedObject(call, size, header[len(MAGIC) :], read)

    async def erase(self, org: str, calls: list[str]) -> int:
        """Delete each call's objects, and its file where one stayed; how many calls had either."""
        deleted: set[str] = set()
        for start in range(0, len(calls), DELETED_AT_ONCE):
            chunk = calls[start : start + DELETED_AT_ONCE]
            gone = await asyncio.gather(*(self._deleted(org, call) for call in chunk))
            deleted |= {call for call, was_there in zip(chunk, gone, strict=True) if was_there}
        return len(deleted | await asyncio.to_thread(_removed, self.root, calls))

    # S3 answers a delete of nothing as it answers a delete: each object is looked for first, so
    # the trail counts the recordings there were.
    async def _deleted(self, org: str, call: str) -> bool:
        found = False
        for name in NAMES:
            what = _object_name(org, call, name)
            if await self.objects.head(self.name, what) is not None:
                await self.objects.delete(self.name, what)
                found = True
        return found


type Recordings = Disk | Bucket


def recordings_of(settings: Settings, http: httpx.AsyncClient) -> Recordings:
    """The bucket PINECALL_RECORDINGS_BUCKET names in the object store, else the disk."""
    root = Path(settings.recordings_root)
    objects = ObjectStore.from_settings(settings, http)
    if settings.recordings_bucket is None or objects is None:
        return Disk(root)
    return Bucket(root, settings.recordings_bucket, objects)


# The worker's pointer says which file it kept, never where: a summary that named any path would
# have the gateway serve any file its own disk holds.
def call_directory(root: Path, call: str) -> Path | None:
    """The call's directory under the root; None for an id that would name a path outside it."""
    directory = (root / call).resolve()
    if directory == root.resolve() or not directory.is_relative_to(root.resolve()):
        return None
    return directory


# Where the worker's session writes the call's audio: the one place a call's file is named.
def recording_path(root: Path, call: str) -> Path:
    """The call's audio file, in a directory of its own under the root; refused outside it."""
    directory = call_directory(root, call)
    if directory is None:
        raise ValidationError(f"call {call!r} names no directory under the recordings root")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / AUDIO_FILE


def kept_on_disk(root: Path, call: str, pointer: str) -> Path | None:
    """The call's recording under the root, by the name its summary gave; None for any other."""
    name = PurePath(pointer).name
    path = (root / call / name).resolve()
    if name not in NAMES or not path.is_relative_to(root.resolve()):
        return None
    return path


def served_sealed(sealed: SealedObject, key: bytes, byte_range: str | None) -> Fetched:
    """A sealed recording as a player reads it: the range it asked for, or the whole, opened."""
    size = recorded_size(sealed.size)
    span = parse_range(byte_range, size)
    if span is not None and span.first >= size:
        return Fetched(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, {"content-range": f"bytes */{size}"}, _nothing())
    whole = span or ByteRange(0, size - 1)
    body = open_range(sealed, key, whole) if size else _nothing()
    headers = {"accept-ranges": "bytes", "content-length": str(whole.length)}
    if span is None:
        return Fetched(HTTPStatus.OK, headers, body)
    return Fetched(
        HTTPStatus.PARTIAL_CONTENT, {**headers, "content-range": f"bytes {span.first}-{span.last}/{size}"}, body
    )


def _object_name(org: str, call: str, name: str) -> str:
    return f"{org}/{call}/{name}"


async def _nothing() -> AsyncIterator[bytes]:
    nothing: tuple[bytes, ...] = ()
    for piece in nothing:
        yield piece


# A recording is a directory named for its call (recording_path): one under the root, whatever
# the id says, or nothing is removed.
def _removed(root: Path, calls: list[str]) -> set[str]:
    removed: set[str] = set()
    for call in calls:
        directory = call_directory(root, call)
        if directory is not None and directory.is_dir():
            shutil.rmtree(directory)
            removed.add(call)
    return removed
