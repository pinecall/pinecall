# pinecall

Build voice and chat agents as Python classes. Annotated fields are the agent's state, `@tool`
methods are what the model can call, docstrings are what it reads about them, and a Jinja view
renders the part of the prompt that changes during the call.

```python
from typing import Literal

from pinecall import Agent, state, tool

from clinica import agenda  # your own system: a CRM, an API, a database


class ClinicaNorte(Agent):
    """You are the front desk of Clínica Norte. Formal, short sentences."""

    stage: Literal["identify", "book"] = "identify"
    patient: dict[str, str] | None = state(None, pii=True)
    slots: list[dict[str, str]] = []

    @tool(stage="identify", pii=("name", "phone"))
    def find_patient(self, name: str, phone: str) -> dict[str, str] | None:
        """Finds the patient by name and phone. Ask for both before calling it."""
        self.patient = agenda.find(name, phone)
        if self.patient:
            self.stage = "book"
        return self.patient

    @tool(stage="book", preview=2)
    def free_slots(self, day: str) -> list[dict[str, str]]:
        """Free slots on one day."""
        self.slots = agenda.free(day)
        return self.slots
```

`views/clinica-norte.jinja`, beside the class, renders the prompt from that state:

```jinja
{% if stage == "identify" %}
Greet the caller and ask for their name and phone. Nothing else until the patient is identified.
{% endif %}
{% if remembers("usual doctor") %}
Offer their usual doctor's slots first.
{% endif %}
{% if slots %}
## Free slots, in order

{% for slot in slots %}
{{ slot.when }} with {{ slot.doctor }}
{% endfor %}
{% endif %}
```

The prompt has four named blocks: `identity`, `knowledge` and `tools` are static and cached
before the history; `view` comes after it and is replaced every turn. A block is re-sent only when
its text changes.

Memory and knowledge-base results never enter the prompt. The platform runs `recall` and `search`
and returns their results to the model as tool results, so retrieved text is treated as data, not
instructions. A view can ask `remembers("usual doctor")` and write its own sentence about the
answer.

## Five minutes

`uv add pinecall`, or `pip install pinecall`. PyPI `pinecall` 0.1.0 to 0.1.5 are the runtime's
releases, before it moved to `pinecall-runtime`: a project pins `pinecall>=0.1.6`.

This package is a library: the verbs are the one `pinecall` CLI's, the same for every language. In
a project laid out as `agents/<name>/agent.py`, with this package in its `.venv`:

```bash
npm i -g pinecall                     # the CLI: Node, whatever the agent is written in
pinecall login                        # this machine signed in, once; pinecall.json names the org
pinecall prompt --state agents/<name>/test/goldens/a.json   # the exact prompt a state produces. No gateway.
pinecall start                        # registered and answering: the process you deploy; leave it running
pinecall chat                         # in another terminal: a caller against the agent start holds
pinecall test                         # ring 1: the goldens, played on the agent start holds, scored by the gateway
```

The CLI never loads your class: for `prompt` and `start` it runs this package's serve entry,
`.venv/bin/python -m pinecall.serve`, and talks to it through the gateway. `start` is the one verb
that runs the agent; `chat`, `test` and `simulate` start nothing, and reach whoever holds it. The
console, the knowledge bases, memory and every other verb are the CLI's. How a server runs
the agent, with the CLI or inside your own Python process, is [docs/production.md](docs/production.md).

## Architecture

This package is the application side. It never talks to a model vendor or handles audio: it sends
commands and reads log entries over one WebSocket, in the runtime's own wire (`pinecall.wire`),
held to the runtime's golden call log. Tools and hooks are the only code that may change state.

| you want | you use |
|---|---|
| the class and the view | `pinecall.Agent`, `pinecall.bridge.mount` |
| the agent held inside your own process | `await pinecall.hold(ClinicaNorte, url=…, api_key=…)` |
| the socket alone, your own way of deciding what to answer | `pinecall.Client` |
| a suite with no network, no key and no model | `pinecall.testing` |

```python
import asyncio
import os

from pinecall import Client
from pinecall.wire.events import UserTurnEnded


async def main() -> None:
    pc = Client("https://cloud.pinecall.io", os.environ["PINECALL_KEY"])
    agent = pc.agent("clinica-norte")

    def heard(event, call):  # every turn.user of every call this socket serves
        if isinstance(event, UserTurnEnded):
            call.say(f"I heard: {event.text}")

    agent.on("turn.user", heard)
    await pc.connect()
    await asyncio.Event().wait()


asyncio.run(main())
```

`PINECALL_KEY` here is a server's token, made in the console's API keys screen for the org and the
environment the process runs in — not your own sign-in, which stays on your machine. On a runtime
of your own the URL is its gateway's (`http://127.0.0.1:8080` on your machine).

## Testing it

Agent tests run with no network, key, model or gateway, in a plain pytest:

```python
from pinecall.testing import Gateway, load

ClinicaNorte = load("agents/clinica-norte/agent.py")

with Gateway() as pc:
    pc.mount(ClinicaNorte)
    call = pc.call_started(from_="+34600123456")
    call.tool("find_patient", name="Marta Ruiz", phone="600123456")

    assert "ask for their name" not in call.prompt
    assert call.tools == ["free_slots"]
```

## Where the rest is

| what | where |
|---|---|
| tutorial: an agent with knowledge and memory, from an empty directory | [docs/tutorial.md](docs/tutorial.md) |
| every file, entity and rule | [ARCHITECTURE.md](ARCHITECTURE.md) |
| how to write an agent, step by step | [docs/writing-an-agent.md](docs/writing-an-agent.md) |
| the view, and the blocks of a prompt | [docs/the-view.md](docs/the-view.md) |
| how to test one | [docs/testing-an-agent.md](docs/testing-an-agent.md) |
| running it in production | [docs/production.md](docs/production.md) |
| the CLI, verb by verb | the one CLI's reference, at docs.pinecall.io |
| a complete example agent | [examples/python/clinica_norte](../../examples/python/clinica_norte) |
| the wire itself | `src/pinecall/wire/`, the runtime's shapes this package speaks |

## Developing

```bash
uv sync
make check        # ruff, pyright strict, deptry, the suite and the example's own
```

## Requirements

Python 3.11+. Runtime dependencies: pydantic, Jinja2, websockets, httpx and typing-extensions. The `pinecall` CLI is
a Node program (Node 24+): the verbs need it, the library does not.

## License

Apache-2.0.
