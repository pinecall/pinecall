"""One served call as the bridge holds it: its instance, what was sent for it, and its jobs."""

import asyncio
import threading
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pinecall._asking import Asking
from pinecall._calls import Call
from pinecall._handoff import Team
from pinecall._screened import Screened
from pinecall.agent import Agent, LastCall
from pinecall.call import CallWorld
from pinecall.wire.parts import ToolSpec

Job = Callable[[], Awaitable[None]]


@dataclass
class Live:
    """One served call: its instance and class, what was last sent, and its jobs, run in order."""

    agent: Agent
    cls: type[Agent]
    world: CallWorld
    call: Call
    asking: Asking
    team: Team | None = None
    rules: Sequence[str] = ()
    last: LastCall | None = None
    # Whether one of the call's classes draws a screen: its state then carries it.
    draws: bool = False
    transfers: list[ToolSpec] = field(default_factory=list[ToolSpec])
    passes: int = 0
    screened: Screened = field(default_factory=Screened)
    sent: dict[str, str] = field(default_factory=dict[str, str])
    tools_shown: str | None = None
    remembered: list[str] = field(default_factory=list[str])
    # A call handed over mid-conversation: the view's `resumed` is true for it from then on.
    resumed: bool = False
    stops: dict[str, Callable[[], None]] = field(default_factory=dict[str, Callable[[], None]])
    warned: set[str] = field(default_factory=set[str])
    # A tool's thread and the loop may both sync: what was sent is read and written under it.
    lock: threading.Lock = field(default_factory=threading.Lock)
    jobs: asyncio.Queue[Job | None] = field(default_factory=asyncio.Queue[Job | None])
    busy: bool = False
    """Whether one of its jobs is running now."""
