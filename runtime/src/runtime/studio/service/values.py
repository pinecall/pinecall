"""The values a definition's `{{…}}` read: a call's own, or a sample of one for a tool tried in the console."""

from typing import Any

from runtime.wire.events import CallStarted

# A call nobody placed: what a tool tried in the console is sent with, every key a real call has.
SAMPLE: dict[str, Any] = {
    "call": {
        "from": "+15550100",
        "to": "+15550199",
        "channel": "web",
        "direction": "inbound",
        "medium": "voice",
        "today": None,
    },
    "caller": {},
    "metadata": {},
}


# `{{metadata.x}}` is what the call was opened with, which `call.started` carries as `metadata`: the
# same thing the exported class reads as `this.call.metadata`. The state a golden or `?state=` opens
# a call in is another thing, and is not read here.
def read_values(started: CallStarted) -> dict[str, Any]:
    """What a Studio agent's `{{…}}` read, from the call's `call.started`."""
    caller = started.caller.model_dump(mode="json", exclude_none=True) if started.caller is not None else {}
    return {
        "call": {
            "from": started.from_,
            "to": started.to,
            "channel": started.channel.value,
            "direction": started.direction.value,
            "medium": started.medium or ("text" if started.channel.value == "whatsapp" else "voice"),
            "today": started.today,
        },
        "caller": caller,
        "metadata": started.metadata or {},
    }


def sample_values(today: str) -> dict[str, Any]:
    """A call's values with nobody on it: every key a real call fills, so a tool tried reads what a call would."""
    return {**SAMPLE, "call": {**SAMPLE["call"], "today": today}}
