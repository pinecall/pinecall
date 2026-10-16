"""The door: what `import pinecall` gives a person writing an agent, and nothing else."""

from pinecall._config import judge as judge
from pinecall._config import knowledge as knowledge
from pinecall._config import llm as llm
from pinecall._config import stt as stt
from pinecall._config import voice as voice
from pinecall._opening import improvise as improvise
from pinecall._opening import words as words
from pinecall._state import Change as Change
from pinecall._state import state as state
from pinecall._tools import tool as tool
from pinecall._version import __version__ as __version__
from pinecall.agent import Agent as Agent
from pinecall.agent import EventMeta as EventMeta
from pinecall.agent import Logged as Logged
from pinecall.blocks import Block as Block
from pinecall.blocks import Blocks as Blocks
from pinecall.blocks import render as render
from pinecall.blocks import show_prompt as show_prompt
from pinecall.call import CallLine as CallLine
from pinecall.call import CallWorld as CallWorld
from pinecall.call import Line as Line
from pinecall.client import Client as Client
from pinecall.errors import DeclarationRefused as DeclarationRefused
from pinecall.errors import DevRefused as DevRefused
from pinecall.errors import NotAStage as NotAStage
from pinecall.errors import NotConnected as NotConnected
from pinecall.errors import PinecallError as PinecallError
from pinecall.errors import Refused as Refused
from pinecall.errors import ToolFailed as ToolFailed
from pinecall.errors import UnauthoredWrite as UnauthoredWrite
from pinecall.errors import WireError as WireError
from pinecall.panels import Drawing as Drawing
from pinecall.panels import Who as Who
from pinecall.panels import panel as panel
from pinecall.serve import hold as hold

__all__ = [
    "Agent",
    "Block",
    "Blocks",
    "CallLine",
    "CallWorld",
    "Change",
    "Client",
    "DeclarationRefused",
    "DevRefused",
    "Drawing",
    "EventMeta",
    "Line",
    "Logged",
    "NotAStage",
    "NotConnected",
    "PinecallError",
    "Refused",
    "ToolFailed",
    "UnauthoredWrite",
    "Who",
    "WireError",
    "__version__",
    "hold",
    "improvise",
    "judge",
    "knowledge",
    "llm",
    "panel",
    "render",
    "show_prompt",
    "state",
    "stt",
    "tool",
    "voice",
    "words",
]


def _owned_by_the_door() -> None:
    # A traceback names `pinecall.PinecallError`, what a person imports, not its private module.
    for name in __all__:
        exported = globals()[name]
        if isinstance(exported, type):
            exported.__module__ = __name__


_owned_by_the_door()
