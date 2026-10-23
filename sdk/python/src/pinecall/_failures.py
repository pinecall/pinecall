"""What a class's own failure leaves on its call: a hook that raised, a view that failed."""

import logging
from collections.abc import Awaitable

from pinecall._calls import Call
from pinecall.wire._names import JsonObject

logger = logging.getLogger("pinecall")

# The custom entries a view that failed to render, and a hook that raised, leave on their call.
RENDER_FAILED = "render.failed"
HOOK_FAILED = "hook.failed"


# A hook that raises fails its call, never the process: the log names the hook and the error, and
# the call goes on with what the hook had written. For `on_event`, `event` is the name it handled.
async def hooked(
    call: Call, hook: str, running: Awaitable[object], *, event: str | None = None
) -> None:
    """Await a hook's run; what it raised is the call's log's and the process's warning."""
    try:
        await running
    except Exception as failed:  # noqa: BLE001 - a class's own failure is the call's, never the loop's
        said: JsonObject = {"hook": hook, "error": type(failed).__name__, "message": str(failed)}
        if event is not None:
            said["event"] = event
        call.log(HOOK_FAILED, said)
        logger.warning("%s: %s raised and the call goes on: %s", call.id, hook, failed)


def unrendered(call: Call, failed: Exception) -> None:
    """A view that cannot be rendered fails its call: the model keeps the view it had."""
    call.log(RENDER_FAILED, {"error": type(failed).__name__, "message": str(failed)})
    logger.warning(
        "%s could not render its view and goes on with the one it had: %s", call.id, failed
    )
