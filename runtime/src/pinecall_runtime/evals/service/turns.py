"""When the caller may speak: the agent's answer read off the log, spoken or written."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from pinecall_runtime.calls import service as calls
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import AgentStateChanged

# The caller's next line and whether it hangs up after it, given the turns left.
type NextLine = Callable[[int], Awaitable[tuple[str, bool]]]
# Told each time the agent's answer lands; it may land again if the answer goes on.
type Landed = Callable[[], None]
# Wait until the agent answered this many lines, telling `Landed` as it lands; True when it did,
# False when the call ended or the agent never answered.
type Wait = Callable[[int, Landed], Awaitable[bool]]

LISTENING = "listening"
SPEAKING = "speaking"

# Longer than the lag between a state and its entry, shorter than a caller's pause.
A_BEAT_S = 0.75
# The quiet a person leaves once the other has stopped. An answer holds only after it: a tool's
# call, or the request that follows a tool's result, lands on the log a moment after the agent
# went back to `listening`, and a caller that spoke in that moment talked over the answer.
A_QUIET_AFTER_S = 1.0
# What the caller waits on: what the agent says and does, and the caller's own turns. The VAD's
# metrics land about once a second all call long; a quiet counted over every entry never passed
# but by chance, and the caller answered seconds after the agent had stopped.
CONVERSATION = calls.Filter(
    types=frozenset(
        {"agent.state", "agent.transcript", "turn.agent", "turn.user", "tool.call", "tool.result", "call.ended"}
    )
)
# An agent that listens in silence this long, nothing of it landing on the log, has no answer:
# the caller goes on. An agent speaking or thinking, or a tool of its running, is waited for.
A_SILENCE_MAY_LAST_S = 30.0
# The most one answer is waited for whatever the agent is doing: a worker that hung mid-turn.
AN_ANSWER_MAY_TAKE_S = 180.0
# An agent that only listens this long opens with nothing.
A_SILENT_OPENING_S = 3.0
AN_OPENING_MAY_TAKE_S = 15.0


def is_call_over(entries: Sequence[Entry]) -> bool:
    """Whether somebody hung up: every end lands as call.ended."""
    return any(entry.type == "call.ended" for entry in entries)


def is_line_open(entries: Sequence[Entry], now: float) -> bool:
    """Whether the agent finished its opening, or has none, and listens."""
    states = [(index, entry) for index, entry in enumerate(entries) if entry.type == "agent.state"]
    if not states:
        return False
    spoke = [index for index, entry in enumerate(entries) if entry.type == "turn.agent"]
    index, last = states[-1]
    if spoke:
        return _state_of(last) == LISTENING and index > spoke[-1]
    only_listened = all(_state_of(entry) == LISTENING for _, entry in states)
    return only_listened and now - states[0][1].ts >= A_SILENT_OPENING_S


# Turn counts lie: livekit speaks a tool's preamble as a turn of its own, and some ears end a
# turn per sentence. A state alone lies too: livekit publishes `listening` while a tool runs, and
# between one tool and the next. The agent having SPOKEN since the caller's last line, and being
# back to listening after it with no tool running, is the signal.
def has_answer_landed(entries: Sequence[Entry], lines: int, *, since: float) -> bool:
    """Whether every line reached the agent, and it spoke and listens again after the last."""
    heard = [index for index, entry in enumerate(entries) if entry.type == "turn.user"]
    # A snapshot older than the caller's silence would answer with the turn before.
    if not heard or entries[heard[-1]].ts < since or len(heard) < lines:
        return False
    if _is_a_tool_running(entries):
        return False
    spoke = [index for index, entry in enumerate(entries) if entry.type == "turn.agent"]
    if not spoke or spoke[-1] < heard[-1]:
        return False
    states = [(index, entry) for index, entry in enumerate(entries) if entry.type == "agent.state"]
    if not states:
        return False
    index, last = states[-1]
    return index > spoke[-1] and _state_of(last) == LISTENING


def is_agent_busy(entries: Sequence[Entry]) -> bool:
    """Whether the agent is on the line: thinking, speaking, or a tool of its running."""
    if _is_a_tool_running(entries):
        return True
    states = [entry for entry in entries if entry.type == "agent.state"]
    return bool(states) and _state_of(states[-1]) != LISTENING


# Read off the log as it grows, never on a timer: a fixed wait talked over tool answers, and a
# cap on the whole answer talked over a long one. Only an agent silent on the line is given up on.
# The log's own clock stamps its entries, so it is the clock the caller's silence is read by:
# `since` is when the caller began its line, before the agent could have heard it.
async def answered(
    logs: calls.Logs, call: str, lines: int, *, since: float | None = None, landed: Landed | None = None
) -> bool:
    """Wait until the agent answered `lines` lines (its opening when 0): True, or False if not."""
    if since is None:
        since = logs.store.clock()
    subscription = await logs.reading(call).follow(CONVERSATION)
    loop = asyncio.get_running_loop()
    started = loop.time()
    moved_at = started
    opening = lines == 0
    quiet_after = A_BEAT_S if opening else A_QUIET_AFTER_S
    at_most = AN_OPENING_MAY_TAKE_S if opening else AN_ANSWER_MAY_TAKE_S
    was_done = False
    try:
        while loop.time() - started < at_most:
            entries = await logs.store.whole(call)
            if is_call_over(entries):
                return False
            done = (
                is_line_open(entries, logs.store.clock()) if opening else has_answer_landed(entries, lines, since=since)
            )
            if done and not was_done and landed is not None:
                landed()
            was_done = done
            quiet = loop.time() - moved_at
            # A state reaches the log late: an answer holds only once the quiet has passed.
            if done and quiet >= quiet_after:
                return True
            silent = not opening and not done and not is_agent_busy(entries)
            if silent and quiet >= A_SILENCE_MAY_LAST_S:
                return False
            # An answer in hand waits out exactly the quiet it lacks, not a whole beat past it.
            within = min(A_BEAT_S, quiet_after - quiet) if done else A_BEAT_S
            if await _moved(subscription, within):
                moved_at = loop.time()
    finally:
        subscription.close()
    return False


# A caller that cuts in waits for the agent to start answering, never for it to finish.
async def speaking(logs: calls.Logs, call: str, *, since: float) -> None:
    """Wait until the agent starts speaking after `since`, or the call ended."""
    subscription = await logs.reading(call).follow(CONVERSATION)
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        while loop.time() - started < AN_ANSWER_MAY_TAKE_S:
            entries = await logs.store.whole(call)
            if is_call_over(entries):
                return
            if any(
                entry.type == "agent.state" and entry.ts >= since and _state_of(entry) == SPEAKING for entry in entries
            ):
                return
            await _moved(subscription, A_BEAT_S)
    finally:
        subscription.close()


# Each line is asked for the moment the agent's answer lands, so the model writes it while the quiet
# after the answer passes, never after it. An answer that goes on (the tool after a preamble)
# throws the line away and asks again; a call that ended uses none of it.
async def speak_turns(turns: int, next_line: NextLine, say: Callable[[str], Awaitable[None]], wait: Wait) -> int:
    """Say each line once the agent answered the last, the first after its opening; the count."""
    spoken = 0
    if turns <= 0:
        await wait(0, _ignored)
        return spoken
    line, hanging_up = await _asked_while(wait, 0, turns, next_line)
    while line:
        await say(line)
        spoken += 1
        if hanging_up:
            break
        if spoken == turns:
            # The last line's answer is heard out; nothing more is asked.
            await wait(spoken, _ignored)
            break
        line, hanging_up = await _asked_while(wait, spoken, turns - spoken, next_line)
    return spoken


async def _asked_while(wait: Wait, lines: int, left: int, next_line: NextLine) -> tuple[str, bool]:
    pending: list[asyncio.Future[tuple[str, bool]]] = []

    def landed() -> None:
        for earlier in pending:
            earlier.cancel()
        pending.append(asyncio.ensure_future(next_line(left)))

    try:
        heard_out = await wait(lines, landed)
    except BaseException:
        await _dropped(pending)
        raise
    ahead = pending.pop() if pending and heard_out else None
    await _dropped(pending)
    return await (next_line(left) if ahead is None else ahead)


async def _dropped(pending: Sequence[asyncio.Future[tuple[str, bool]]]) -> None:
    for line in pending:
        line.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


def _ignored() -> None:
    return None


def _state_of(entry: Entry) -> str:
    return AgentStateChanged.model_validate(entry.data).state


# livekit publishes `listening` while a tool runs, so a call with no result yet is mid-turn.
def _is_a_tool_running(entries: Sequence[Entry]) -> bool:
    called = {str(entry.data.get("call_id")) for entry in entries if entry.type == "tool.call"}
    answered_ids = {str(entry.data.get("call_id")) for entry in entries if entry.type == "tool.result"}
    return bool(called - answered_ids)


async def _moved(subscription: calls.Subscription, within_s: float) -> bool:
    try:
        await asyncio.wait_for(anext(subscription), within_s)
    except (TimeoutError, StopAsyncIteration):
        return False
    return True
