"""A WebSocket refused or ended with a reason the client reads, within what a close frame carries."""

from fastapi import WebSocket

from pinecall_runtime.exceptions import PinecallError

# RFC 6455 §7.4.2 leaves 4000 to 4999 to the application: a refusal closes with 4000 plus the status
# it would have answered over HTTP, so a client reads 4404 as the 404 it is.
A_REFUSAL = 4000
# RFC 6455 §5.5: a longer close reason drops the connection with no close frame.
CLOSE_REASON_BYTES = 123


def close_reason(sentence: str) -> str:
    """The sentence cut to what a close frame carries."""
    return sentence.encode("utf-8")[:CLOSE_REASON_BYTES].decode("utf-8", errors="ignore")


# A close before the handshake is a bare 403 with no reason: the socket is accepted first.
async def refuse_socket(websocket: WebSocket, refused: PinecallError) -> None:
    """Accept the socket and close it at once, the refusal its reason and its status its code."""
    await websocket.accept()
    await websocket.close(code=code_of(refused), reason=close_reason(str(refused)))


def code_of(refused: PinecallError) -> int:
    """The close code of a refusal: 4000 plus its status."""
    return A_REFUSAL + refused.status


def authorization_of_socket(websocket: WebSocket) -> str | None:
    """The secret the socket's Authorization header carries as a Bearer."""
    scheme, _, value = websocket.headers.get("authorization", "").partition(" ")
    return (value.strip() or None) if scheme.lower() == "bearer" else None
