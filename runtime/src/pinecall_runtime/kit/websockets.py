"""A WebSocket refused or ended with a reason the client reads, within what a close frame carries."""

from fastapi import WebSocket

# RFC 6455 §7.4.1: the code a server closes with when the client broke the policy.
POLICY_VIOLATION = 1008
# RFC 6455 §5.5: a longer close reason drops the connection with no close frame.
CLOSE_REASON_BYTES = 123


def close_reason(sentence: str) -> str:
    """The sentence cut to what a close frame carries."""
    return sentence.encode("utf-8")[:CLOSE_REASON_BYTES].decode("utf-8", errors="ignore")


# A close before the handshake is a bare 403 with no reason: the socket is accepted first.
async def refuse_socket(websocket: WebSocket, why: str) -> None:
    """Accept the socket and close it at once with the refusal as its reason."""
    await websocket.accept()
    await websocket.close(code=POLICY_VIOLATION, reason=close_reason(why))


def authorization_of_socket(websocket: WebSocket) -> str | None:
    """The secret the socket's Authorization header carries as a Bearer."""
    scheme, _, value = websocket.headers.get("authorization", "").partition(" ")
    return (value.strip() or None) if scheme.lower() == "bearer" else None
