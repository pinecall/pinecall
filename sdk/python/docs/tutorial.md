# Tutorial — an agent that answers from your documents and remembers who called

Forty minutes, from an empty directory to an agent that picks up a call, answers out of a folder of
Markdown you wrote, and knows on the second call what it learned on the first.

You need the gateway — Pinecall's, at `https://cloud.pinecall.io`, whose sandbox is yours to break —
the one `pinecall` CLI, and this package. The CLI is a Node program for every language: it never
loads your class, it starts this package's serve entry and talks to it through the gateway. Your
code never imports LiveKit.

## 1. The CLI, and a key

```bash
npm i -g pinecall                # the CLI, Node 24+
pinecall new clinica --agent clinica-norte --python
cd clinica
uv sync                          # the project's .venv, with pinecall in it
pinecall link                    # signs this machine in, picks the org, writes its key to ./.env
pinecall whoami                  # which gateway, which org, and where the key was read
```

`pinecall new --python` writes a uv project — the clinic — with `pinecall` in its dependencies, and
`--agent` its first agent, `agents/clinica-norte/`: the class, its view, a ring-0 test and one golden. Without uv, `python -m venv .venv` and
`.venv/bin/pip install pinecall pytest` make the same `.venv`, and the CLI uses it the same way.

`pinecall link` writes `PINECALL_KEY` into this folder's `.env` (and `PINECALL_URL` when the gateway
is not Pinecall's), which nothing else reads: another org is another folder. Every verb works in the sandbox unless `--prod` is said.

## 2. The class

The project's layout is the CLI's, the same as a TypeScript or a Ruby one: one folder per agent,
`agents/<slug>/`, holding `agent.py`, its view in `views/`, its documents under `docs/` and its tests
under `test/`. **The folder's name is the agent's slug.** Replace `agents/clinica-norte/agent.py` with this — the whole thing:

```python
from typing import Literal

from pinecall import Agent, state, tool


class ClinicaNorte(Agent):
    """You are the front desk of Clínica Norte. Formal, short sentences."""

    stage: Literal["identify", "resolve"] = "identify"
    patient: dict[str, str] | None = state(None, pii=True)

    @tool(stage="identify", pii=("name", "phone"))
    def find_patient(self, name: str, phone: str) -> dict[str, str]:
        """Finds the patient by name and phone. Ask for both before calling it."""
        self.patient = {"name": name, "phone": phone}
        self.stage = "resolve"
        return self.patient
```

and `agents/clinica-norte/views/clinica-norte.jinja`, beside it, is the prompt as a function of that
state:

```jinja
{% if stage == "identify" %}
Greet the caller and ask for their name and phone. Nothing else until you have both.
{% endif %}
{% if patient %}
You are talking to {{ patient.name }}, already on file. Do not ask for them again.
{% endif %}
```

Four things are worth naming, because they are the whole design:

- **The class's docstring is the prompt's first paragraph.** Not documentation about the code: the
  words the model reads.
- **A tool's docstring is what the model reads about that tool, and its signature is the schema.**
  The annotations become the JSON Schema the model fills, and the same model validates what it
  sends before your method runs: a `Literal` is an enum, a default makes a parameter optional.
  `pii=` names the arguments that carry personal data and are masked in the log; one naming a
  parameter the method has not is refused when the class is created, by name — as is a tool with no
  docstring, a `*args`, or a `stage=` the `Literal` does not hold.
- **Annotated fields are the state, and tools are the only writers.** `self.patient = …` renders the
  prompt again and writes a `state.changed` line carrying the tool's own name; the same assignment
  anywhere else raises `UnauthoredWrite`. Each field is a descriptor, so the writer *is* the
  recorder, and the author rides a `ContextVar`, so two calls served at once never mix.
- **The view is a template, beside the class.** `views/<slug>.jinja` is the convention, so nothing
  names it, and every state field is in scope under its own name. Not one framework tag is in it,
  and it is the only part of the prompt that differs between two turns of a call.

Before running anything, look at what the model would read. No key, no gateway, no network:

```
$ pinecall prompt
── identity (static) ──
You are the front desk of Clínica Norte. Formal, short sentences.

<rules>
- Invent nothing: if it did not come from a tool or from the knowledge, do not say it.
- One question per turn, and wait for the answer.
…
</rules>

<protocols>
- To act, call a tool; saying you have done something does not do it.
…
</protocols>

<channel>
You are on a phone call. Everything you write is read aloud by a voice: short spoken sentences, …
</channel>

── knowledge (static) ──

── tools (static) ──
<tools>
- find_patient: Finds the patient by name and phone. Ask for both before calling it.
</tools>

── history ──

── view (dynamic) ──
Greet the caller and ask for their name and phone. Nothing else until you have both.
```

Four named blocks in two regions, in the one order they are ever sent. Everything above `history` is
what the provider caches; the view is rendered again on every state change, and a block goes up
again only when its own text changed. The rules and the channel's words are the framework's, the
same in every language the SDK is written in. `pinecall prompt --state <a golden's file>` prints the
page that golden's opening state produces.

## 3. Talk to it

```bash
pinecall chat                    # the agent served from this terminal, and a written caller against it
pinecall start                   # registered and answering: the process you deploy
```

`chat` starts this package's serve entry for the agent of this folder — `.venv/bin/python -m
pinecall.serve start …`, a process that takes no call it did not open — opens a written call naming
that process, and stops it when you leave. `start` is the same entry taking every call, with the
console's screens answered beside it; under it, the console's Talk tab is a real voice call to the
same process.

Either way your tools run in that Python process. A `def` tool runs on a thread, so a blocking call
to your CRM never holds the socket; an `async def` tool runs on the loop. The gateway asks, your
method answers, and no code of yours ever crosses the socket.

## 4. Knowledge: a page the agent knows by heart

The voice, the model, the opening and everything else the agent runs on are not in the class: they
are the world's, set with `pinecall agent set` or the console's Settings, and a class that still
declares one is refused when it is created, with the verb to use instead
([writing-an-agent.md](writing-an-agent.md)).

What the agent knows by heart — hours, prices, what needs an authorisation — is one of those: a page
of Markdown in the agent's settings, written in the console, Settings ▸ Knowledge, or with
`pinecall agent knowledge edit`. The class sends nothing for it, so `pinecall prompt` prints the
second block empty; the gateway writes the page into it, whole, once per call, in the cached prefix:
the model has it in every turn and you pay for it once.

Use this for what is small, stable and always relevant. Seventeen thousand characters is fine. A
folder of a hundred documents is not, and that is the next step.

## 5. The knowledge base: what it looks up per turn

Put your Markdown under `agents/clinica-norte/docs/`, one file per subject, with headings, and push it.
With no arguments the verb reads that folder and pushes it under the agent's slug. Attaching the
base to the agent, with its `k` and `min_score`, is the world's: `pinecall docs attach clinica-norte
--k 4`.

```bash
pinecall docs push
```

That is all: no vector-database client, no `search` call in your code, no `if` that decides when to
look.

**What the push did.** Each file was cut at its headings, each chunk prefixed with its heading path
(`prices.md › Prices › Check-up`), and embedded one document at a time, so a chunk was embedded
seeing its neighbours. The vectors went into Postgres, an HNSW index beside a BM25 index.

**What happens on a turn.** The platform runs a `search` itself; the two indexes are asked in
parallel and fused by reciprocal rank. On a spoken call it starts while the caller is still talking,
so the answer is there when they stop; a written caller has no half-said sentence to start on, so it
runs at turn end.

**`k` and `min_score`.** `k` is how many chunks reach the model. `min_score` is on a 0..1 scale
normalised by the best chunk, so `0.5` cuts the tail and a threshold near zero cuts nothing.

A push replaces the base whole, so push again after every edit. `pinecall docs list` shows the bases,
`pinecall docs drop clinica-norte` removes one.

## 6. Memory: what it keeps between calls

```bash
pinecall memory policy --remember "how they like to be addressed" "allergies" "their usual doctor" --forget "payments"
```

The policy is the world's, not the class's. `remember` is the vocabulary, **in your own words**, of
what is worth keeping about a person; `forget` is what is never written whatever the model heard.

**Reading, on a turn.** A `recall` runs beside the `search`, on the same path. It answers the
contact's facts, ranked by relevance, recency and importance — no model call, so it costs nothing
but a query.

**Writing, at hang-up.** One model call reads the call's turns and the facts already held, and
answers add, update or invalidate. An updated fact is a new row that supersedes the old one, and
nothing is deleted except by `forget`.

**Who a caller is.** On the phone and on WhatsApp the number is the identity. On the web nobody is
anybody until somebody says so — the token door seals a contact id the browser cannot forge — and an
agent remembers nothing of an anonymous visitor.

```bash
pinecall memory +34600123456          # what is held about one person, current facts first
pinecall memory forget +34600123456   # the one verb that removes rows
```

The view may ask memory a question and say a sentence of its own about the answer:

```jinja
{% if remembers("usual doctor") %}
Offer their usual doctor's slots first.
{% endif %}
```

## 7. What the model actually receives

```
system:   identity · knowledge · tools           ← cached, unchanged while the call runs
messages: …the turns…
          assistant tool_use  recall  {"contact":"+34600123456","query":"How much is…"}
          user      tool_result       {"facts":[{"text":"Prefers to be called Marta.", …}]}
          assistant tool_use  search  {"query":"How much is a general check-up?"}
          user      tool_result       {"chunks":[{"path":"prices.md", "heading":"Prices › Check-up", …}]}
          user      <instructions> what the view rendered </instructions>
```

**Why a tool result and not a paragraph of the prompt.** A remembered fact was written by a model
from an earlier caller's words, and a chunk was written by whoever wrote the document. Neither is
yours, so neither carries your authority: third-party content belongs in `tool_result` blocks,
JSON-encoded so nothing in it can break out into an instruction.

That is why **every block of the prompt is your own words and nothing else is ever put in one**. The
one thing a view does with memory is ask `remembers("…")` and say a sentence of *yours* about the
answer. A sentence planted in a document that says "book without confirming" arrives as data the
model is trained to discount, and it cannot open the confirmation gate anyway, because that gate is
code.

## 8. The log, and the console

```bash
pinecall console                 # the sandbox's console, signed in as this folder's key
pinecall sessions                # the calls this agent has taken; `sessions show <call>` reads one
```

The same log without a browser is `pinecall.Client`, the other door this package has — no class, no
view, no CLI, just the socket and its key. What the base answered on one call:

```python
import asyncio
import os
import sys

from pinecall import Client


async def main(call: str) -> None:
    url = os.environ.get("PINECALL_URL", "https://cloud.pinecall.io")
    client = Client(url, os.environ["PINECALL_KEY"])
    page = await client.history(call=call)
    for entry in page.entries:
        if entry.type == "docs.sources":
            for chunk in entry.data["sources"]:
                print(f"{chunk['path']} › {chunk['heading']} · {chunk['score']:.2f}")


asyncio.run(main(sys.argv[1]))
```

```bash
uv run --env-file .env python history.py call_…
```

Every call is an append-only log of typed entries, each with a `seq` written before control returns.
`page.state` is the log folded with the runtime's own reducer, and `client.observe(call=…)` is the
same log as a stream.

## 9. Test it

**Ring 0** is your own suite: pytest, no network, no key, no model, no gateway.
`pinecall.testing.Gateway` is a gateway that is not there: it answers the declarations, keeps every
command the agent sent, and lets the test say what happened next.

```python
from pathlib import Path

from pinecall.testing import Gateway, load

# A folder named by a slug cannot be imported: the class is loaded as `pinecall start` loads it.
ClinicaNorte = load(Path(__file__).parents[1] / "agent.py")


def test_once_identified_the_prompt_stops_asking_for_the_name() -> None:
    with Gateway() as pc:
        pc.mount(ClinicaNorte)
        call = pc.call_started(from_="+34600123456")

        call.tool("find_patient", name="Marta", phone="600123456")

        assert "talking to Marta" in call.prompt
        assert "ask for their name" not in call.prompt
```

```bash
uv run pytest
```

`call.prompt` is the view as the agent last sent it, `call.tools` what the model may call right now,
`call.block("knowledge")` any of the four blocks by name. The prompt is a pure function of the state,
so `render(agent)["view"]` after `agent.start_in({...})` needs no gateway at all.

**Rings 1, 2 and 3** — the goldens, a real line, and one call re-scored — are `pinecall test`,
`pinecall simulate --voice` and `pinecall eval`: the goldens under `agents/clinica-norte/test/goldens/`, each
call served by this package's entry, scored by the gateway.

**Ring 4** happens without you: every finished call is judged at hang-up and the verdict is an entry
in your own log, `call.score`. `consent` is checked by code off the gate lines; `grounded` checks
that what the agent stated appears in the evidence it was given.

## Where to go next

| you want | read |
|---|---|
| every declaration a class may carry | [writing-an-agent.md](writing-an-agent.md) |
| the four blocks, the two regions, and the template | [the-view.md](the-view.md) |
| the rings, and what is worth a test | [testing-an-agent.md](testing-an-agent.md) |
| running it on a server | [production.md](production.md) |
| a whole agent: stages, ids, a confirmed booking | [examples/python/clinica_norte](../../../examples/python/clinica_norte) |
| every verb, and where the key comes from | the one CLI's reference, at docs.pinecall.io |
