"""A recording sealed under its own key: AES-GCM a chunk at a time, so a range opens on its own."""

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pinecall_runtime.exceptions import UpstreamError

MAGIC = b"PCSEAL1\n"
PREFIX_BYTES = 8
# A chunk of audio as recorded: a range opens the chunks it covers and no other.
CHUNK = 64 * 1024
TAG = 16
# The last chunk is sealed as the last, so a file cut short never opens as a shorter recording.
LAST, MORE = b"\x01", b"\x00"
KEY_BITS = 256
HEADER = len(MAGIC) + PREFIX_BYTES
SEALED_CHUNK = CHUNK + TAG

type Reader = Callable[[int, int], AsyncIterator[bytes]]


@dataclass(frozen=True, slots=True)
class SealedObject:
    """A sealed recording where it is kept: its sealed size, its nonces' prefix, and its reader."""

    call: str
    size: int
    prefix: bytes
    read: Reader


@dataclass(frozen=True, slots=True)
class ByteRange:
    """First and last byte of the recording as recorded, both included."""

    first: int
    last: int

    @property
    def length(self) -> int:
        """How many bytes."""
        return self.last - self.first + 1


def new_key() -> bytes:
    """A recording's own key."""
    return AESGCM.generate_key(bit_length=KEY_BITS)


def seal_file(plain: Path, sealed: Path, key: bytes) -> None:
    """Write `sealed` from `plain` a chunk at a time, then remove `plain`. Blocking: run in a thread."""
    cipher = AESGCM(key)
    prefix = os.urandom(PREFIX_BYTES)
    part = sealed.with_name(f"{sealed.name}.part")
    with plain.open("rb") as source, part.open("wb") as target:
        target.write(MAGIC + prefix)
        chunk, index = source.read(CHUNK), 0
        while True:
            following = source.read(CHUNK)
            target.write(cipher.encrypt(_nonce(prefix, index), chunk, MORE if following else LAST))
            if not following:
                break
            chunk, index = following, index + 1
        target.flush()
        os.fsync(target.fileno())
    part.rename(sealed)
    plain.unlink()


def recorded_size(sealed_size: int) -> int:
    """How many bytes the recording had, from its sealed object's size."""
    full, rest = divmod(sealed_size - HEADER, SEALED_CHUNK)
    return full * CHUNK + max(rest - TAG, 0)


def parse_range(header: str | None, size: int) -> ByteRange | None:
    """The one range a player asked for within the recording; None for the whole of it."""
    if header is None or not header.startswith("bytes=") or "," in header:
        return None
    first, _, last = header.removeprefix("bytes=").strip().partition("-")
    if not (first or last) or not all(bound.isdigit() for bound in (first, last) if bound):
        return None
    if not first:
        return ByteRange(max(size - int(last), 0), size - 1)
    if last and int(last) < int(first):
        return None
    return ByteRange(int(first), min(int(last), size - 1) if last else size - 1)


async def open_range(sealed: SealedObject, key: bytes, span: ByteRange) -> AsyncIterator[bytes]:
    """The span's bytes as recorded, opening only the chunks it covers, one at a time."""
    chunks = -(-(sealed.size - HEADER) // SEALED_CHUNK)
    first, last = span.first // CHUNK, span.last // CHUNK
    start = HEADER + first * SEALED_CHUNK
    end = min(HEADER + (last + 1) * SEALED_CHUNK, sealed.size)
    cipher = AESGCM(key)
    index = first
    async for piece in _in_chunks(sealed.read(start, end - start)):
        flag = LAST if index == chunks - 1 else MORE
        try:
            plain = cipher.decrypt(_nonce(sealed.prefix, index), piece, flag)
        except InvalidTag:
            raise UpstreamError(f"the sealed recording of {sealed.call} does not open: chunk {index}") from None
        low = span.first - index * CHUNK if index == first else 0
        high = span.last - index * CHUNK + 1 if index == last else len(plain)
        yield plain[low:high]
        index += 1


async def on_disk(call: str, path: Path) -> SealedObject | None:
    """The sealed file at the path, read a chunk at a time off the loop; None when absent."""
    try:
        header, size = await asyncio.to_thread(_head_of, path)
    except FileNotFoundError:
        return None
    if not header.startswith(MAGIC):
        raise UpstreamError(f"the sealed recording of {call} does not open: {path} is not sealed")

    async def read(offset: int, length: int) -> AsyncIterator[bytes]:
        with await asyncio.to_thread(path.open, "rb") as file:
            await asyncio.to_thread(file.seek, offset)
            left = length
            while left > 0:
                piece = await asyncio.to_thread(file.read, min(SEALED_CHUNK, left))
                if not piece:
                    return
                left -= len(piece)
                yield piece

    return SealedObject(call, size, header[len(MAGIC) :], read)


def _head_of(path: Path) -> tuple[bytes, int]:
    with path.open("rb") as file:
        return file.read(HEADER), path.stat().st_size


def _nonce(prefix: bytes, index: int) -> bytes:
    return prefix + index.to_bytes(4, "big")


async def _in_chunks(pieces: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    waiting = bytearray()
    async for piece in pieces:
        waiting += piece
        while len(waiting) >= SEALED_CHUNK:
            yield bytes(waiting[:SEALED_CHUNK])
            del waiting[:SEALED_CHUNK]
    if waiting:
        yield bytes(waiting)
