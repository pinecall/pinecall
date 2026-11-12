"""Where a call's audio is kept: the disk it was recorded on, or a bucket, under its org; and a range of it as asked."""

import asyncio
import shutil
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

from runtime.exceptions import UpstreamError, ValidationError
from runtime.kit.s3 import ObjectStore
from runtime.kit.sealed_file import (
    HEADER,
    MAGIC,
    ByteRange,
    SealedObject,
    on_disk,
    open_range,
    parse_range,
    plain_size_of,
)

# The recorder's file in the call's own directory: `<root>/<call>/audio.ogg` on the disk,
# `<org>/<call>/audio.ogg` in the bucket. Sealed under the call's own key, it is `audio.sealed`
# beside it (kit/sealed_file.py): the name says which a stored recording is.
AUDIO_FILE = "audio.ogg"
SEALED_FILE = "audio.sealed"
# Every object a call's recording may be kept as.
NAMES = (AUDIO_FILE, SEALED_FILE)

# An org's erasure deletes its calls' objects this many at a time.
DELETED_AT_ONCE = 16
# A plain file on the disk is read this much at a time, off the loop.
READ_AT_ONCE = 64 * 1024

# Reads so many bytes of a recording from an offset.
type Read = Callable[[int, int], AsyncIterator[bytes]]


# What is read, and no word of HTTP: the endpoint says 200, 206 or 416 and writes the headers from
# this. Until 2026-11 the status and the headers were built here, twice.
@dataclass(frozen=True, slots=True)
class Ranged:
    """A recording as a player reads it: its size, the range asked for when one was, and the bytes."""

    size: int
    # None: the whole recording.
    span: ByteRange | None
    body: AsyncIterator[bytes]

    @property
    def satisfiable(self) -> bool:
        """Whether the range asked for starts inside the recording; the whole always does."""
        return self.span is None or self.span.first < self.size

    @property
    def length(self) -> int:
        """How many bytes the body carries."""
        if not self.satisfiable:
            return 0
        return self.size if self.span is None else self.span.length


def read_range(size: int, byte_range: str | None, read: Read) -> Ranged:
    """The range a player asked for of a recording of this size, or the whole of it; nothing of one past its end."""
    span = parse_range(byte_range, size)
    if span is not None and span.first >= size:
        return Ranged(size, span, _nothing())
    whole = span or ByteRange(0, size - 1)
    return Ranged(size, span, read(whole.first, whole.length) if size else _nothing())


def open_sealed(sealed: SealedObject, key: bytes, byte_range: str | None) -> Ranged:
    """A sealed recording as a player reads it: the range it asked for, or the whole, opened."""
    size = plain_size_of(sealed.size)
    return read_range(
        size, byte_range, lambda first, length: open_range(sealed, key, ByteRange(first, first + length - 1))
    )


@dataclass(frozen=True, slots=True)
class Disk:
    """Recordings kept on the disk they were recorded on: a box with no bucket, as always."""

    root: Path

    async def store(self, org: str, call: str, audio: Path) -> None:
        """Nothing to do: the recorder's file is where it is kept."""

    async def fetch(self, _org: str, call: str, byte_range: str | None) -> Ranged | None:
        """The plain recording on this disk, the range asked for when one is; None while it is not here."""
        path = _file_of(self.root, call, AUDIO_FILE)
        size = None if path is None else await asyncio.to_thread(_size_of, path)
        if path is None or size is None:
            return None
        return read_range(size, byte_range, lambda first, length: _read_file(path, first, length))

    async def find_sealed(self, _org: str, call: str) -> SealedObject | None:
        """The call's sealed file on this disk, read by ranges; None while it is not here."""
        path = _file_of(self.root, call, SEALED_FILE)
        return None if path is None else await on_disk(call, path)

    async def erase(self, _org: str, calls: list[str]) -> int:
        """Remove each call's recording directory; how many calls had one. The disk knows no org."""
        return len(await asyncio.to_thread(_remove, self.root, calls))


# The disk holds a recording until it is uploaded, and keeps one whose upload failed: what the
# bucket lacks is looked for there, so whoever asks for a recording asks one place.
@dataclass(frozen=True, slots=True)
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
        await asyncio.to_thread(_remove, self.root, [call])

    async def fetch(self, org: str, call: str, byte_range: str | None) -> Ranged | None:
        """The plain recording, the range asked for when one is: the bucket's, else this disk's; None with neither."""
        what = _object_name(org, call, AUDIO_FILE)
        size = await self.objects.head(self.name, what)
        if size is None:
            return await Disk(self.root).fetch(org, call, byte_range)
        return read_range(
            size, byte_range, lambda first, length: self.objects.read(self.name, what, offset=first, length=length)
        )

    async def find_sealed(self, org: str, call: str) -> SealedObject | None:
        """The call's sealed object, read by ranges: the bucket's, else this disk's; None while neither has it."""
        what = _object_name(org, call, SEALED_FILE)
        size = await self.objects.head(self.name, what)
        if size is None:
            return await Disk(self.root).find_sealed(org, call)
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
            gone = await asyncio.gather(*(self._delete(org, call) for call in chunk))
            deleted |= {call for call, was_there in zip(chunk, gone, strict=True) if was_there}
        return len(deleted | await asyncio.to_thread(_remove, self.root, calls))

    # S3 answers a delete of nothing as it answers a delete: each object is looked for first, so
    # the trail counts the recordings there were.
    async def _delete(self, org: str, call: str) -> bool:
        found = False
        for name in NAMES:
            what = _object_name(org, call, name)
            if await self.objects.head(self.name, what) is not None:
                await self.objects.delete(self.name, what)
                found = True
        return found


# Built once by the process that keeps recordings (the gateway, a worker), from its settings: the
# bucket PINECALL_RECORDINGS_BUCKET names in the object store, else the disk.
type Recordings = Disk | Bucket


# The worker's pointer says which file it kept, never where: a summary that named any path would
# have the gateway serve any file its own disk holds.
def name_of(pointer: str) -> str | None:
    """The recording's file as its call's summary names it; None for any name a recording is never kept as."""
    name = PurePath(pointer).name
    return name if name in NAMES else None


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


def _file_of(root: Path, call: str, name: str) -> Path | None:
    directory = call_directory(root, call)
    return None if directory is None else directory / name


def _size_of(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return None


async def _read_file(path: Path, offset: int, length: int) -> AsyncIterator[bytes]:
    with await asyncio.to_thread(path.open, "rb") as file:
        await asyncio.to_thread(file.seek, offset)
        left = length
        while left > 0:
            piece = await asyncio.to_thread(file.read, min(READ_AT_ONCE, left))
            if not piece:
                return
            left -= len(piece)
            yield piece


def _object_name(org: str, call: str, name: str) -> str:
    return f"{org}/{call}/{name}"


async def _nothing() -> AsyncIterator[bytes]:
    nothing: tuple[bytes, ...] = ()
    for piece in nothing:
        yield piece


# A recording is a directory named for its call (recording_path): one under the root, whatever
# the id says, or nothing is removed.
def _remove(root: Path, calls: list[str]) -> set[str]:
    removed: set[str] = set()
    for call in calls:
        directory = call_directory(root, call)
        if directory is not None and directory.is_dir():
            shutil.rmtree(directory)
            removed.add(call)
    return removed
