"""The door: what `import pinecall` gives a person writing an agent, and nothing else."""

from pinecall._config import judge as judge
from pinecall._config import knowledge as knowledge
from pinecall._config import llm as llm
from pinecall._config import realtime as realtime
from pinecall._config import stt as stt
from pinecall._config import voice as voice
from pinecall._harness import judges as judges
from pinecall._harness import own_judge as own_judge
from pinecall._harness import own_persona as own_persona
from pinecall._harness import personas as personas
from pinecall._opening import improvise as improvise
from pinecall._opening import words as words
from pinecall._state import Change as Change
from pinecall._state import state as state
from pinecall._tools import tool as tool
from pinecall._version import __version__ as __version__
from pinecall.agent import Agent as Agent
from pinecall.agent import EventMeta as EventMeta
from pinecall.agent import Logged as Logged
from pinecall.app import Heard as Heard
from pinecall.app import VoiceApp as VoiceApp
from pinecall.app import voice_app as voice_app
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
from pinecall.flows import Called as Called
from pinecall.flows import Flow as Flow
from pinecall.flows import FlowChanged as FlowChanged
from pinecall.flows import Step as Step
from pinecall.flows import StepUnwritten as StepUnwritten
from pinecall.flows import flow as flow
from pinecall.panels import Drawing as Drawing
from pinecall.panels import Who as Who
from pinecall.panels import panel as panel
from pinecall.screen import Part as Part
from pinecall.screen import Shown as Shown
from pinecall.screen import part as part
from pinecall.serve import hold as hold
from pinecall.tasks import GetEmail as GetEmail
from pinecall.tasks import GetName as GetName
from pinecall.tasks import GetPhone as GetPhone
from pinecall.tasks import Task as Task
from pinecall.tasks import task as task

__all__ = [
    "Agent",
    "Block",
    "Blocks",
    "CallLine",
    "CallWorld",
    "Called",
    "Change",
    "Client",
    "DeclarationRefused",
    "DevRefused",
    "Drawing",
    "EventMeta",
    "Flow",
    "FlowChanged",
    "GetEmail",
    "GetName",
    "GetPhone",
    "Heard",
    "Line",
    "Logged",
    "NotAStage",
    "NotConnected",
    "Part",
    "PinecallError",
    "Refused",
    "Shown",
    "Step",
    "StepUnwritten",
    "Task",
    "ToolFailed",
    "UnauthoredWrite",
    "VoiceApp",
    "Who",
    "WireError",
    "__version__",
    "flow",
    "hold",
    "improvise",
    "judge",
    "judges",
    "knowledge",
    "llm",
    "own_judge",
    "own_persona",
    "panel",
    "part",
    "personas",
    "realtime",
    "render",
    "show_prompt",
    "state",
    "stt",
    "task",
    "tool",
    "voice",
    "voice_app",
    "words",
]


def _owned_by_the_door() -> None:
    # A traceback names `pinecall.PinecallError`, what a person imports, not its private module.
    for name in __all__:
        exported = globals()[name]
        if isinstance(exported, type):
            exported.__module__ = __name__


_owned_by_the_door()
