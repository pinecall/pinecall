"""Reading a request's body with a ceiling, so an upload over it never lands whole in memory."""

from fastapi import Request

from pinecall_runtime.exceptions import PayloadTooLarge


# Read a chunk at a time and stopped just past the ceiling: the request is refused before the
# rest of it is read.
async def capped_body(request: Request, most: int, what: str) -> bytes:
    """The body whole, or PayloadTooLarge once more than `most` bytes came in."""
    read = bytearray()
    async for chunk in request.stream():
        read += chunk
        if len(read) > most:
            raise PayloadTooLarge(f"{what} is {most // (1024 * 1024)} MiB at most")
    return bytes(read)
