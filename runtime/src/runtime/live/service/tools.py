"""A worker's tool call, run through the app that holds its agent, and what it answered."""

from runtime.exceptions import Conflict, NotFound
from runtime.live.holders import Holders
from runtime.live.served import Calls, Served
from runtime.live.sockets import Sockets
from runtime.session import service as session
from runtime.wire.events import ToolCall
from runtime.wire.parts import ToolResult

NOT_OPEN = "this gateway is not writing call {call!r}: open it with POST /v1/calls first"
NO_APP_FOR_THE_TOOL = "no app holds agent {slug}: its tools cannot run until one does"


# The gateway writes tool.call and tool.result: appending the call is what reaches the app.
async def run_tool(
    calls: Calls, sockets: Sockets, holders: Holders, served: Served, agent: str, tool_call: ToolCall
) -> ToolResult:
    """Run a worker's tool call through the app that holds its agent, and answer its result."""
    if agent != served.agent:
        raise NotFound(NOT_OPEN.format(call=served.call))
    # Parked because nobody holds the agent: a refusal now, not a wait until the tool's deadline.
    if served.app is None and holders.find_holder(served.scope, agent) is None:
        raise Conflict(NO_APP_FOR_THE_TOOL.format(slug=agent))
    # Its socket is on another gateway, which may never have heard the call was bound to it.
    if served.app is not None and not sockets.is_here(served.app):
        calls.start_pump(served.call, after=0)
    use = session.ToolUse(call_id=tool_call.call_id, name=tool_call.name, arguments=dict(tool_call.arguments))
    return await served.tools.run(use, tool_call.speech_id)
