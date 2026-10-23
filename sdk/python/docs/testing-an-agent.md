# Testing an agent

Ring 0 is the ring your own suite lives in: no network, no key, no model, no gateway. It runs on
every commit, in a second, and it is where nearly every mistake is caught.

```python
from pathlib import Path

from pinecall.testing import Gateway, load

# A folder named by a slug cannot be imported: the class is loaded as `pinecall start` loads it,
# its folder a package, so `agent.py` imports what sits beside it with `from .agenda import …`.
ClinicaNorte = load(Path(__file__).parents[1] / "agent.py")


def test_a_patient_on_file_is_not_asked_for_their_name_again() -> None:
    with Gateway() as pc:
        pc.mount(ClinicaNorte)
        call = pc.call_started(from_="+34600123456")

        assert "You are talking to Marta Ruiz" in call.prompt
        assert call.tools == ["free_slots"]
```

`pinecall.testing.Gateway` is a gateway that is not there. It answers the declarations, keeps
every command the agent sent, and lets the test say what happened next; each step returns once the
agent has finished answering it. It needs no plugin: a plain `def test_…` drives it, and the
`with` block closes the loop it runs on.

## Driving a call

| you write | what happens |
|---|---|
| `pc.call_started(from_=, channel=, medium=, id_=, state=)` | a call opens, `on_call` runs, then `state=` (what `call.started` carries when a golden or a persona opened it) is written over the hook's, and the first prompt goes out. Returns the handle |
| `call.tool("free_slots", day="Tuesday")` | the model calls a tool. Returns the `tool.result` the agent sent back: `output`, or `error` |
| `call.said("Tuesday works for me")` | the caller said something |
| `call.fact("agenda.changed", {"slots": []})` | a fact from your backend; `source="participant"` for a browser |
| `call.ended()` | the call is over, `on_end` runs |
| `pc.call_attached(state, id_=)` | a call handed over mid-conversation: no `on_call`, the state the gateway kept, the whole prompt sent |
| `pc.finds(Found(path, heading, text), …)` | what every search answers with; `pc.searched` is what was asked, `(call, query, k)` each |

## Asking what the agent said

| you read | what it is |
|---|---|
| `call.prompt` | the `view` block as the agent last sent it: the last thing the model reads |
| `call.block("identity")` | any of the four blocks as the agent last sent it, by name; `""` until it had something to say |
| `call.tools` | the tools the model may call right now, by name |
| `call.state` | the state as the agent last sent it |
| `call.commands` | everything sent on this call, in order |
| `call.last("call.log", name="cita")` | the last command of one type whose fields match |
| `mounted.instance_of(call.id)` | the instance itself, for an assertion about a field |
| `pc.errors` | what failed with nobody waiting for it — an empty list is an assertion worth making |

## What is worth a test

The things a prompt makes true, not the things a method returns:

```python
def test_a_phone_call_offers_two_slots() -> None:
    with Gateway() as pc:
        pc.mount(ClinicaNorte)
        call = pc.call_started(from_="+34600123456", channel="phone")
        call.tool("free_slots", day="Tuesday", specialty="family medicine")

        assert "Offer at most two" in call.prompt


def test_a_slot_nobody_offered_is_refused_instead_of_booked() -> None:
    with Gateway() as pc:
        pc.mount(ClinicaNorte)
        call = pc.call_started(from_="+34600123456")
        call.tool("free_slots", day="Tuesday", specialty="family medicine")

        assert "is not one of the slots" in str(call.tool("propose", slot="Sunday")["error"])
```

A tool that raises is not a broken test: the model is waiting for an answer and reads the message
as the tool's own result, so `call.tool(...)` gives you back `{"error": "…"}` and the call carries
on. That is what you assert on.

## Without mounting anything

The prompt is a function of the state, so most assertions need no gateway at all:

```python
from pinecall import CallLine, CallWorld, render

agent = ClinicaNorte().seal()
agent.serving(CallWorld(CallLine(id="CA_1", channel="phone", today="2026-09-17")))
agent.start_in({"stage": "book", "slots": [slot]})

assert "Tuesday at ten" in render(agent)["view"]
assert agent.run_tool("propose", {"slot": "s-1"}) == slot
```

`start_in` writes the fields a case names over the ones the class gave itself; `restore` means
something stronger, a whole state, so a field it leaves out is cleared. `run_tool` runs a tool as
a call does — its arguments checked and converted, its writes authored, its list cut to its
`preview` — and runs an `async def` tool to its end.

## The rings above

The verbs are the one `pinecall` CLI's (npm), the same for a Python project as for a TypeScript or
a Ruby one, in the same layout: `agents/<slug>/agent.py`, `agents/<slug>/test/goldens/`,
`agents/<slug>/test/memory/`, `agents/<slug>/docs/`. Only `pinecall start` and `pinecall prompt` start
this package's serve entry, `python -m pinecall.serve`, with the project's own interpreter; the
others start nothing and reach whoever holds the agent.

| ring | what it asks | how |
|---|---|---|
| 1 | does the agent hold its goldens? | `pinecall test` — the goldens under `agents/<slug>/test/goldens/`, played on whoever holds the agent: your `pinecall start`, or production's with `--prod` |
| 2 | does it hold on a real line? | `pinecall test --voice` · `pinecall simulate --voice` |
| 3 | what does one real call score? | `pinecall eval <call-id>` |
| 4 | what did every call score? | `call.score`, written by the runtime at hang-up |

The index and memory have goldens of their own — whether retrieval returns the chunk a question
needs (`pinecall docs eval`), whether recall brings back the fact a question needs
(`pinecall memory eval`), and what the hang-up's one model call writes, replaces and must never
keep (`pinecall remember`, the cases in `agents/<slug>/test/memory/`). They are files beside the
project, run by the CLI and the same for every language: [Testing knowledge and memory](https://docs.pinecall.io/guides/testing-knowledge-and-memory/).
