# Writing an agent

An agent is one Python class. Everything the model can see about it comes from four places: the
class's docstring, what the class declares, the docstrings of its tools, and the view.

```python
from typing import Literal

from pinecall import Agent, state, tool


class ClinicaNorte(Agent):
    """You are the front desk of Clínica Norte. Formal, short sentences.
    Everything you say is read aloud: no lists, no markdown."""
```

That docstring is the `identity` block of the prompt — the first of the static blocks, which never
change during a call and are what a provider caches. Write it as instructions to a person, not as
documentation. It reaches the model on one line, its blank lines dropped.

## Config: what the agent *is*

Written on the class, unannotated or as a `ClassVar`, because it is not something the agent
remembers. It never changes during a call and no view renders it.

| written | what it does |
|---|---|
| `channel_rules = False` | leaves out the `<channel>` part of the prompt: how to write for a voice, a website's chat, WhatsApp |
| `slug = "front-desk"` | the name the agent registers as; left out, the folder's name under `pinecall start`, or the class's name in kebab-case (`ClinicaNorte` → `clinica-norte`) in your own process. A class served under another slug is refused |
| `accepts = {"slot.released": ["app"]}` | the outside events the agent takes, and from whom: `app` is your backend, `participant` a browser in the call |

### The environment: the settings', or the class's

Everything the agent **runs on** is its settings': set per world, versioned, with who set it and
why, and changed without a deploy — by `pinecall agent set`, the console's Configure screen, or the
verb the table names. The class may declare any of them instead, and **what the class declares
wins**: the settings of that field are not read for the agent, the console shows it locked, "set by
the class", and a `pinecall agent set` of it is refused naming the class. Take it out of the class
and deploy, and the settings apply again.

```python
from typing import ClassVar

from pinecall import Agent, judge, llm, stt, voice


@voice("cartesia", "a0e99841-438c-4a64-b679-ae501e7d6091", model="sonic-2")
@llm(
    "openai/gpt-5.4-mini", temperature=0.3, builds="responses.LLM", options={"use_websocket": True}
)
@stt("soniox/stt-rt-v3", end_of_turn="smart-turn")
@judge("openai/qwen3-32b", options={"base_url": "http://gpu:8000/v1"})
class ClinicaNorte(Agent):
    """Recepción de Clínica Norte: da, cambia y cancela turnos."""

    language = "es"
    greeting = "Clínica Norte, buenas, ¿en qué le ayudo?"
    hangup = "the caller says goodbye or needs nothing else"
```

`greeting` is the words, said as written — instant, and no model runs — or the model's own:
`greeting = improvise` opens on the prompt alone, `greeting = improvise("Saludá por el nombre si lo
sabés")` with an instruction for the opening. The caller cannot cut it short unless it says so:
`improvise("…", interruptible=True)`, or `words("…", interruptible=True)` for words. `hangup` is
when the model may end the call, in your words, or `hangup = True` whenever it judges the call
done. `@stt` also takes `end_of_turn=`, who says the caller's turn is over: `"stt"` the ears
themselves (Deepgram Flux; refused for ears that cannot), `"livekit"` or `"smart-turn"` (Smart Turn
v3), a model on the worker that runs on any key. Left out, the ears end the turn where they can and Smart Turn v3 does everywhere else.

`@voice`, `@llm`, `@realtime`, `@stt`, `@judge` and `@knowledge` are decorators; the rest are class attributes, plain or annotated
`ClassVar`. An attribute annotated any other way is the call's state, so one of these written that
way is refused when the class is created, with how to declare it; and `knowledge` as an attribute
would hide `self.knowledge.search`, so it is refused for `@knowledge(path=…, text=…)`.

`@llm` and `@stt` take `vendor/model` or a vendor alone; `@voice` the vendor and its own id for the
voice. Each takes `builds=`, a class of the vendor's LiveKit plugin other than its default (a dot
reaches into a module of it: `responses.LLM` is OpenAI's Responses API, and `use_websocket` its
WebSocket), and `options=`, that class's keyword arguments as the plugin names them, passed as given
and over Pinecall's. **Both run only on your org's own key for that vendor**: on a key Pinecall lends
they are refused when the agent registers, naming `pinecall providers add <vendor>`, since an option
can point the plugin at another server. `@llm` also takes `temperature=`, which runs on any key. A
model that hears and speaks itself is not an `@llm`: `@realtime("xai/grok-voice-3.0",
options={"voice": "eve"})` runs the agent's voice calls — phone and web — on it alone, with no ears
and its own voice, while the `@llm` keeps answering the written ones; `pinecall providers` lists the
vendors' realtime models, its options run on your org's own key alone, and an `@llm` that names
such a model is refused at registration. A realtime model that says given words itself (xAI's Grok does) is the call's only voice: the recording notice, a greeting given as words and a confirmation's read-back are said by it, in its own voice; one that cannot leaves them to the agent's voice, and the call then has two. A vendor that is not installed, or does not do the stage, is refused at registration. `@llm` fixes the
whole model: with it on the class, `--temperature`, `--llm-builds` and `--llm-option` are refused too.

`@judge` is the model the agent's calls are judged on at hang-up, over the org's choice and
Pinecall's own: `vendor/model` or a vendor alone, with `builds=` and `options=` as `@llm` takes them.
On a key of your org's own for that vendor — a local model's server among them, through
`options={"base_url": "…"}` — its evals are never billed; on a key Pinecall lends they are. The
judge is asked for a forced tool call, so a local model must call tools.

| field | what it is | on the class | or in the settings |
|---|---|---|---|
| `voice` | the voice: its vendor and the vendor's id | `@voice("<vendor>", "<id>", model=…)` | `pinecall agent set --voice` |
| `llm` | the model that answers, and its temperature | `@llm("<vendor>/<model>", temperature=0.3)` | `pinecall agent set --llm` |
| `realtime` | the model a voice call runs on alone, hearing and speaking itself | `@realtime("<vendor>/<model>", options={…})` | `pinecall agent set --realtime` |
| `stt` | the ears, and who ends the caller's turn | `@stt("<vendor>/<model>", end_of_turn="smart-turn")` | `pinecall agent set --stt` · `--end-of-turn` |
| `judge` | the model the calls are judged on; on your own key its evals are not billed | `@judge("<vendor>/<model>", options={"base_url": "…"})` | the settings' `judge`, `judge_builds`, `judge_options` |
| `language` | the language the call is in | `language = "es"` | `pinecall agent set --language` |
| `greeting` | how the call opens: the words, or the model's own | `greeting = "…"` · `improvise` · `improvise("…")` | `pinecall agent set --greeting '…'` · `--greeting improvise` · `--greeting improvise:'…'` |
| `hangup` | whether the model may end the call itself, and when, in your words | `hangup = "…"` · `True` | `pinecall agent set --hangup '…'` · `--hangup any` |
| `turn` | when the caller has finished, and may interrupt | `turn: ClassVar = {"endpointing_ms": 300}` | `pinecall agent set --endpointing-ms` |
| `says` | how a word the voice would misread is said | `says: ClassVar = [{"word": "DKV", "spoken": "de ka uve"}]` | `pinecall lexicon add <word> --say '…'` |
| `hears` | the words the ears must know: names, brands, the doctor's surname | `hears: ClassVar = ["Vidal", "Sanitas"]` | `pinecall lexicon hear <word> …` |
| `memory` | what to remember about a caller across calls, and what never to | `memory: ClassVar = {"remember": […], "forget": […]}` | `pinecall memory policy --remember '…' --forget '…'` |
| `record` | whether the call is recorded | `record = False` | `pinecall agent set --record on\|off` |
| `max_duration` | the longest a voice call runs, in minutes, or `"off"` | `max_duration = 20` | `pinecall agent set --max-duration 20` |
| `llm_timeout` | how long a turn waits for the model's first word, in seconds | `llm_timeout = 8` | `pinecall agent set --llm-timeout 8` |
| `knowledge` | what the agent knows by heart: a page of Markdown, read whole on every call | `@knowledge(path="knowledge.md", text=…)` | `pinecall agent knowledge edit` |
| `docs` | the base the agent searches per turn | `docs: ClassVar = {"base": "clinica-norte", "k": 4}` | `pinecall docs push`, then `pinecall docs attach <base>` |
| `judges` | which of Pinecall's judges its calls meet, and its own | `judges = judges(on=["consent", …])`, its own as `judges/<name>.md` | `pinecall judges on\|off\|add` |
| `personas` | which of Pinecall's callers its simulations play, and its own | `personas = personas(on=["in-a-hurry", …])`, its own as `test/personas/<name>.json` | `pinecall personas on\|off\|add` |

**The judges and the callers are the class's the same way.** `judges(on=[…])` names which of
Pinecall's judges the agent's calls meet, every other off, and the agent's own judges are the files
under `agents/<slug>/judges/`, one each, in the library's own format: front matter (`answer`,
`choices`, `when`, `trigger`, `reads`) and the question below it, the file's name the judge's.
`personas(on=[…])` is the same for the callers `pinecall simulate` plays, the agent's own under
`agents/<slug>/test/personas/`, one JSON file each, what `PUT …/personas/{name}` takes. The folders
are read beside the class's own file when the agent registers. Declared, the class is the agent's
list: the console shows both locked, "set by the class", and `pinecall judges add` or
`personas add` is refused naming the class; a class that declares neither leaves both to the console
and the CLI, as before. A folder with files beside a class that declares nothing is refused when
the agent registers, saying what to write. The org's own judges (`pinecall judges add --org`) meet
every agent's calls either way.

**Neither a fact the agent remembers nor a chunk of a base ever reaches the prompt.** Both arrive
as a tool result, in the history, where a model reads them as information rather than as an
instruction. A tool that searches calls `self.knowledge.search(…)`; the class says nothing about
it, and the package reads it off the class's file when the agent registers, so a world with no
base attached is refused then rather than at the first turn.

## State: what it remembers

Every annotated attribute whose name does not start with `_` and that is not a `ClassVar` is a
state field. Its value is where every call opens; a list or a dict is copied, so no two calls ever
share one.

```python
class ClinicaNorte(Agent):
    stage: Literal["identify", "choose", "book", "done"] = "identify"
    patient: dict | None = state(pii=True)
    slots: list[dict] = []
    proposed: dict | None = None

    @property
    def identified(self) -> bool:  # derived: in every snapshot, assigned by nobody
        return self.patient is not None
```

- **`stage`** is a `Literal` of the values it may hold, opening at the one written (the first, if
  none is). A tool's `stage=` is checked against it, and setting it to anything else raises
  `NotAStage` — pyright says so before the code runs.
- **`state(...)`** is for a field that also says who may see it: `state(pii=True)`, or
  `state(default, visibility="public")`. Left out, the wire's default applies (`tenant`).
- **A public `@property` is a derived field.** A `cached_property`, a method or a `_name` is a
  collaborator — the agenda, a client — and never state.
- A subclass's own `__init__` needs no `super().__init__()`: the state opens on its first use.

**Tools are the only writers.** Once the agent is sealed — every call seals its instance — a write
anywhere but in a tool or a hook raises `UnauthoredWrite`:

```
state field patient was assigned outside a tool and outside a lifecycle hook; tools are the only writers of state
```

Every write is recorded with its author, the tool's own name, carried by a `ContextVar`: two calls
served at the same moment never read each other's. `agent.changes()` is the record;
`agent.collapse("…")` replaces it with one sentence; `agent.log(name, data)` writes a line of your
own into the call's log.

## Tools: what the model may do

```python
class ClinicaNorte(Agent):
    @tool(stage="identify", pii=("name", "phone"))
    def find_patient(self, name: str, phone: str) -> dict | None:
        """Finds the patient's file by their full name and phone.

        Call it only once the patient has given you both.

        Args:
            name: the full name, as they said it
            phone: the phone number, as they said it
        """
        self.patient = self.agenda.find(name, phone)
        if self.patient:
            self.stage = "choose"
        return self.patient
```

The docstring, up to its first section, is what the model reads to choose the tool; the `Args:`
section is what it reads of each parameter; the annotations are the schema it fills, and what it
sends is checked and converted against them before the method runs: a `Literal` is an enum, a
pydantic model a nested object, `"3"` for an `int` is `3`. A parameter with no annotation is
`str` — what a person on the phone says.

| option | what it does |
|---|---|
| `stage=` | visible while the state is in this stage, or one of these: `stage=("choose", "book")` |
| `when=` | a question asked of the agent on every change: `when=lambda self: bool(self.slots)` |
| `confirm=` | the sentence said after the tool runs. **This is what makes a tool irreversible on the wire**; `{{result.x}}` names a field of what it returns |
| `announce=` | what the agent says as the tool starts ("Let me check the agenda."), when the model's turn said nothing itself and wrote no line of its own in the argument `say` every tool carries; a turn that spoke first is not announced twice. No tool declares an argument named `say` |
| `preview=` | how many rows of a list the *model* sees. The state keeps every row |
| `pii=` | the parameters that carry personal data: the log masks their values wherever the agent wrote them down (`state.changed`, `tool.result` and a line you log too), and `pinecall start` prints the log's version. A callback's number is what the callback is for, so `callback.requested` keeps it in the clear |
| `timeout=` | how many seconds the platform waits for this method |

A tool may be a `def` or an `async def`. In a call, an `async def` runs on the event loop and a
`def` on a thread of its own, so a blocking call to your systems never holds the socket; both
write as the tool. In a test, `agent.run_tool("find_patient", {"name": "Ana", "phone": "600…"})`
runs either to its end, as a call would.

## The hooks

```python
class ClinicaNorte(Agent):
    def on_call(self, call: CallWorld) -> None:  # a call started; writes here are the hook's
        self.patient = self.agenda.by_phone(call.from_ or "")
        if self.patient:
            self.stage = "choose"

    def on_end(self, call: CallWorld) -> None:  # a line logged here still lands
        self.log("outcome", {"stage": self.stage})

    def on_event(
        self, name: str, data: JsonObject, meta: EventMeta
    ) -> None: ...  # an accepted outside fact
    def on_memory(self, ops: list[MemoryOp], call: CallWorld) -> None: ...  # memory read or written
```

After `on_end` the SDK sends `call.done`, and the gateway waits for it, up to three seconds, before it
seals the call: a log is closed to lines once sealed, so a line `on_end` logs later than that is refused,
and the gateway's journal names it.

A hook that raises fails its call and no other: the call's log gets a `hook.failed` line naming the
hook (and the event, for `on_event`) and the error, the process one warning, and the call goes on
with what the hook had written.

Each may be a `def` or an `async def`. `on_call` runs before the first prompt goes out, so the
model never reads a state the call was not in; the state a golden or a persona opens the call in
is applied after it, so the hook never overwrites it. An outside fact reaches `on_event` only if
the class `accepts` the pair — an event declared from `app` that arrives from a browser is
somebody else's event with your name on it, and the hook never sees it.

## The call

Inside a tool or a hook, `self.call` is the live call; outside one it says so rather than being
`None`.

```python
self.say("One moment, let me check.")  # an Answer: True once the turn lands, False after 30 s
self.reply("Tell them it is booked.")  # the model speaks, guided by words nobody hears
self.call.send("cart", {"total": 42})  # a payload to the browsers in the room
self.call.participant(identity).mute()  # and .remove()
self.call.invite("+34910000001")  # a phone leg; invite(identity, "participant") for a seat
self.call.transfer("+34910000002")  # an Answer: a Transferred, ok=False if they are still here
self.call.attention("wants to talk to a person", wait_s=60)  # an Attended: who took the line
self.call.hold()  # and unhold()
self.call.dtmf("1#")
self.call.claim("4821")  # the page showing 4821 follows this call; call.claimed says so
self.call.callback("+34600000001", when="tomorrow afternoon", note="a quote")
self.call.opt_out("does not want more calls")  # their number joins the do-not-call list
self.call.hangup("done")
self.knowledge.search("summer opening hours", k=3)  # an Answer: the chunks, searched for this call
```

**A verb that waits answers with an `Answer`.** In an `async def` tool, `await` it; in a `def`
tool, which runs on a thread of its own, `.result()` waits for it there — or leave it, and the
command still goes. It is settled by the entry that says how it went, by its ceiling, or by the
call ending first (`ok=False`, `the call ended before it was answered`).

There is no LiveKit here and no escape hatch to it: a need the room cannot express is a new
command with a name.

## The panel beside a conversation: `@panel`

The console draws a pane beside every thread in **Calls**. Without a panel it is what the console
itself knows — how many conversations there have been with this person, what they came in by, how
long the agent spent on the line with them. A class that declares a panel has **its own drawn over
that**, and that is where the business's data goes: the customer's file, their orders, the balance.

```python
from pinecall import Agent, Drawing, Who, panel


class ClinicaNorte(Agent):
    @panel("Customer")
    def file(self, who: Who, draw: Drawing) -> None:
        client = self.crm.find(who.contact)
        if client is None:
            with draw.panel("Not on file"):
                draw.text("Not in the CRM.")
            return
        with draw.panel(client.name):
            with draw.rows():
                draw.row("Since", client.since)
                draw.row("Area", client.area)
            draw.stat("Jobs", len(client.jobs))
            draw.table(["date", "job", "amount"], client.jobs)
            draw.badge("owes" if client.debt else "paid up", tone="warn" if client.debt else "good")
```

It is the TypeScript package's `@view`, and what reaches the console is the same: a tree of the
closed catalogue — `panel`, `rows`, `row`, `stat`, `table`, `badge`, `text` — drawn by the console's
own parts, in the theme the person reading chose; nothing a tenant writes reaches the page's
styling, its scripts or its key. `who` is the conversation — `agent`, `contact`, `call` — and nothing
else: the panel is read beside threads that ended weeks ago, so it fetches what it shows, on an
instance of its own, never from a call's state. It may be an `async def`. A table's row is a
sequence in the columns' order or a mapping keyed by them; a number is written whole when it is
whole, and `None` or a boolean draws nothing. One per class, and a subclass does not inherit it.

## What is refused when the class is created

Every one of these raises `DeclarationRefused` on the file's import — never in the middle of a
call, and never as a refusal from a gateway:

| refused | the sentence |
|---|---|
| a tool with no docstring | `without a docstring no model can choose it` |
| `def book(self, *chosen)`, `**kwargs`, or a positional-only parameter | `a model fills a JSON object by name, so every parameter is one it can name` |
| `pii=("dni",)` on a tool with no `dni` | `pii names parameters the tool has; unknown: dni` |
| `stage="pay"` where the `Literal` has no `"pay"` | `pay is not one of this agent's stages (identify, book)` |
| `stage=` on a class with no `stage` | `…declares none; add stage: Literal["identify", "book"] to the class` |
| `stage: str` | `stage names the values it may hold: stage: Literal["identify", "book"]` |
| a tool with an argument named `say`, which every tool carries for the model's own line | `bad_shape: tool echo: 'say' is the platform's argument, never a tool's own`, said by the gateway when `pinecall start` registers the agent, not on import |
| a field named like the agent's own (`snapshot`, `log`, `call`…) | `` `snapshot` is a name the agent itself uses; call the field otherwise`` |
| a tool named like the agent's own method | `a tool named so would hide the agent's own log` |
| an `accepts` sender that is not `app` or `participant` | `'browser' sends nothing; an event comes from app or participant` |
| `state(pii=True, visibility="public")` | `a field is pii or public, not both` |
| two `@panel` methods | `declares two panels (Customer and Orders); a class draws one panel` |
| a `@panel` method that does not take `(self, who, draw)` | `a panel draws with (self, who, draw)` |
| `language: str = "es"` (annotated as state) | `` `language` is the class's, not a call's state: declare it as a class attribute, `language = …` or `language: ClassVar = …` `` |
| `knowledge = {…}` | `` `knowledge` is the class's, not a call's state: declare it as @knowledge(path="…", text="…") `` |
| both `@llm(…)` and an `llm` attribute | `ClinicaNorte declares both @llm(…) and a llm attribute; keep one` |
| a judge file with no question, a bad `answer`, a `choice` with one choice, a `trigger` with no question | `offers.md: a judge asks a question of a call: write one below the front matter`, … |
| a persona file with no `goal` or `style`, or a key the wire does not know | `in-a-rush.json: a persona wants something: write its goal, in the first person` |
| `judges/` or `test/personas/` with files, and a class that declares neither | `agents/x/judges holds 2 judge(s) and the class declares none: judges = judges(on=["consent", …]) declares them, and which of Pinecall's run` |
