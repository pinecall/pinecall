# Writing an agent

An agent is one TypeScript class, the default export of `agents/<slug>/agent.tsx`. Everything the
model can see about it comes from four places: the docstring above the class, what the class
declares, the docstrings of its tools, and `render()`.

```tsx
import { Agent } from "@pinecall/agents";

/**
 * You are the front desk of Clínica Norte. Formal, short sentences.
 * Everything you say is read aloud: no lists, no markdown.
 */
export default class ClinicaNorte extends Agent {}
```

That docstring is the `identity` block of the prompt — the first of the static blocks, which never
change during a call and are what a provider caches. Write it as instructions to a person, not as
documentation. It must be a `/** … */` comment directly above the class: the CLI hands the class
its own source, so the comment survives compilation. `static doc = "…"` says it instead, for a
build that strips comments.

## Config: what the agent *is*

Written on the class, because it is not something the agent remembers. It never changes during a
call and no view renders it.

| written | what it does |
|---|---|
| `channelRules = false` | leaves out the `<channel>` part of the prompt: how to write for a voice, a website's chat, WhatsApp |
| `static slug = "front-desk"` | the name the agent registers as; left out, the folder's name under `pinecall start`, or the class's name in kebab-case (`ClinicaNorte` → `clinica-norte`) under `mount`. A class served under another slug is refused |
| `static events: EventDeclarations = { "slot.released": { from: ["app"] } }` | the outside events the agent takes, and from whom: `app` is your backend, `participant` a browser in the call. The type is there because TypeScript reads `["app"]` in a bare literal as `string[]` |

### The environment: the settings', or the class's

Everything the agent **runs on** is its settings': set per world, versioned, with who set it and
why, and changed without a deploy — by `pinecall agent set`, the console's Configure screen, or the
verb the table names. The class may declare any of it instead, and **what the class declares wins**:
the settings of that field are not read for the agent, the console shows it locked, "set by the
class", and a set of it is refused naming the class. Take it out of the class to set it again.

```tsx
@voice("cartesia", "a0e99841-438c-4a64-b679-ae501e7d6091", { model: "sonic-2" })
@llm("openai/gpt-5.4-mini", { temperature: 0.3, builds: "responses.LLM", options: { use_websocket: true } })
@stt("soniox/stt-rt-v3", { endOfTurn: "smart-turn" })
export default class ClinicaNorte extends Agent {
  static language = "es";
  static greeting = "Clínica Norte, buenas, ¿en qué le ayudo?";
  static hangup = "the caller says goodbye or needs nothing else";
}
```

`greeting` is the words, said as written — instant, and no model runs — or the model's own:
`improvise` opens on the prompt alone, `improvise("Greet them by name if you know it")` with an
instruction for the opening. The caller cannot cut it short unless it says so:
`improvise("…", { interruptible: true })`, or `{ text: "…", interruptible: true }` for words.
`hangup` is when the model may end the call, in your words, or `true` whenever it judges the call
done. `@stt` also takes `endOfTurn`, who says the caller's turn is over: `"stt"` the ears
themselves (Deepgram Flux; refused for ears that cannot), `"livekit"` or `"smart-turn"` (Smart Turn
v3), a model on the worker that runs on any key. Left out, the ears end the turn where they can and Smart Turn v3 does everywhere else.

`@judge` names the model the agent's calls are judged on, over the org's choice and the platform's:
on a key of your org's own its evals are never billed, a local model included —
`@judge("openai/qwen3-32b", { options: { base_url: "http://gpu:8000/v1" } })` — and it must call
tools, since every judge answers through one.

`@llm`, `@stt` and `@judge` take `vendor/model` or a vendor alone; `@voice` the vendor and its own id for the
voice. Each takes `builds`, a class of the vendor's livekit plugin other than its default (dotted
names reach a module of it: `responses.LLM` is OpenAI's Responses API, and `use_websocket` its
WebSocket), and `options`, that class's keyword arguments as the plugin names them, passed as given
and over the operator's. **Both run only on your org's own key for that vendor**: on a key Pinecall
lends they are refused at registration, naming `pinecall providers add <vendor>`, since an option
can point the plugin at another server. `@llm` also takes `temperature`, which runs on any key. A
model that hears and speaks itself is not an `@llm`: `@realtime("xai/grok-voice-3.0", { options: {
voice: "eve" } })` runs the agent's voice calls — phone and web — on it alone, with no ears and its
own voice, while the `@llm` keeps answering the written ones; `pinecall providers` lists the
vendors' realtime models, its options run on your org's own key alone, and an `@llm` that names
such a model is refused at registration. A realtime model that says given words itself (xAI's Grok does) is the call's only voice: the recording notice, a greeting given as words and a confirmation's read-back are said by it, in its own voice; one that cannot leaves them to the agent's voice, and the call then has two. A vendor that is not installed, or does not do the stage, is refused at registration. A decorator
fixes the whole stage: with `@llm` in the class, `--temperature`, `--llm-builds` and `--llm-option`
are refused too. The settings take the same knobs for a class that leaves the stage to them
(`pinecall agent set --temperature 0.3 --llm-builds responses.LLM --llm-option use_websocket=true`). The rest are `static` fields: an instance field is the call's state, so one of these
declared there is refused when the class loads.

| field | what it is | on the class | or in the settings |
|---|---|---|---|
| `voice` | the voice: its vendor and the vendor's id | `@voice("<vendor>", "<id>")` | `pinecall agent set --voice` |
| `llm` | the model that answers, and its temperature | `@llm("<vendor>/<model>", { temperature })` | `pinecall agent set --llm` |
| `realtime` | the model a voice call runs on alone, hearing and speaking itself | `@realtime("<vendor>/<model>", { options })` | `pinecall agent set --realtime` |
| `stt` | the ears, and who ends the caller's turn | `@stt("<vendor>/<model>", { endOfTurn })` | `pinecall agent set --stt` · `--end-of-turn` |
| `judge` | the model its calls are judged on | `@judge("<vendor>/<model>", { options })` | `pinecall agent set --judge` |
| `language` | the language the call is in | `static language = "es"` | `pinecall agent set --language` |
| `greeting` | how the call opens: the words, or the model's own | `static greeting = "…"` · `improvise` · `improvise("…")` | `pinecall agent set --greeting '…'` · `--greeting improvise` · `--greeting improvise:'…'` |
| `hangup` | whether the model may end the call itself, and when, in your words | `static hangup = "…"` · `true` | `pinecall agent set --hangup '…'` · `--hangup any` |
| `turn` | when the caller has finished, and may interrupt | `static turn = { endpointingMs: 300 }` | `pinecall agent set` |
| `says` | how a word the voice would misread is said | `static says = [{ word, spoken }]` | `pinecall lexicon add <word> --say '…'` |
| `hears` | the words the ears must know: names, brands, the doctor's surname | `static hears = ["…"]` | `pinecall lexicon hear <word> …` |
| `memory` | what to remember about a caller across calls, and what never to | `static memory = { remember: […], forget: […] }` | `pinecall memory policy --remember '…' --forget '…'` |
| `record` | whether the call is recorded | `static record = false` | `pinecall agent set --record on\|off` |
| `maxDuration` | the longest a voice call runs, in minutes, or `"off"` | `static maxDuration = 20` | `pinecall agent set --max-duration 20` |
| `llmTimeout` | how long a turn waits for the model's first word, in seconds | `static llmTimeout = 8` | `pinecall agent set --llm-timeout 8` |
| `knowledge` | what the agent knows by heart: a page of Markdown, read whole on every call | `static knowledge = { path, text }` | `pinecall agent knowledge edit` |
| `docs` | the base the agent searches per turn; declared, the folder `agents/<slug>/docs/` is pushed into it when the agent registers | `static docs = { base: "…", k: 4 }` | `pinecall docs push`, then `pinecall docs attach <base>` |
| `judges` | which of Pinecall's judges its calls meet, and its own | `static judges = judges({ on: ["consent", …] })`, its own as `judges/<name>.md` | `pinecall judges on\|off\|add` |
| `personas` | which of Pinecall's callers its simulations play, and its own | `static personas = personas({ on: ["in-a-hurry", …] })`, its own as `test/personas/<name>.json` | `pinecall personas on\|off\|add` |

**The judges and the callers are the class's the same way.** `judges({ on })` names which of
Pinecall's judges the agent's calls meet, every other off, and the agent's own judges are the files
under `agents/<slug>/judges/`, one each, in the library's own format: front matter (`answer`,
`choices`, `when`, `trigger`, `reads`) and the question below it, the file's name the judge's.
`personas({ on })` is the same for the callers `pinecall simulate` plays, the agent's own under
`agents/<slug>/test/personas/`, one JSON file each, what `PUT …/personas/{name}` takes. Declared,
the class is the agent's list: the console shows both locked, "set by the class", and
`pinecall judges add` or `personas add` is refused naming the class; a class that declares neither
leaves both to the console and the CLI, as before. A folder with files beside a class that declares
nothing is refused when the class loads, saying what to write. The org's own judges
(`pinecall judges add --org`) meet every agent's calls either way.

**Neither a fact the agent remembers nor a chunk of a base ever reaches the prompt.** Both arrive
as a tool result, in the history, where a model reads them as information rather than as an
instruction. A tool that searches calls `this.knowledge.search(…)`; the class says nothing else
about it, and a class that reads `this.knowledge` is refused at registration when no base is
attached, rather than at the first turn.

## State: what it remembers

Every own field of the instance is state, and so is every getter. Each call gets its own instance,
so field initializers run once per call and two callers never share a list.

```tsx
import { Agent, state, type Stages } from "@pinecall/agents";

export default class ClinicaNorte extends Agent {
  @state stage: Stages<"identify" | "choose" | "book" | "done"> = "identify";
  @state({ pii: true }) patient?: Patient | undefined;
  @state slots: Slot[] = [];
  @state proposed?: Slot | undefined;

  get identified() {          // derived: in every snapshot, assigned by nobody
    return this.patient !== undefined;
  }

  private agenda() {          // a method is a collaborator, never state
    return new Agenda();
  }
}
```

- **`stage`** is typed with `Stages<…>`, which names its values once: a tool's `stage` uses the same
  words, and a misspelled stage is a compile error.
- **`@state`** says who may see a field: `@state({ pii: true })` masks it in the log,
  `@state({ visibility: "public" })` lets a participant's browser read it, and bare `@state` is the
  default, `tenant`. **Decorating one field decides them all**: a class with no `@state` has every
  field as state, and a class with any has those and nothing else. An undecorated field is then
  scratch space, out of the prompt, the log and goldens — `stage` included, so the tools it gates
  would never show. Decorate every field, or none.
- **A getter is state**, read every time the state is copied. A collaborator belongs in a method.

**Tools and hooks are the only writers.** Once the agent is sealed — every call seals its instance —
a write anywhere else throws `UnauthoredWrite`:

```
state field patient was assigned outside a tool and outside a lifecycle hook; tools are the only writers of state
```

Every write is recorded with its author — the tool's name, `hook:onCall`, `event:<name>` — carried
by `AsyncLocalStorage`, so two calls served at the same moment never read each other's.
`this.collapse("…")` replaces the record with one sentence; `this.log(name, data)` writes a line of
your own into the call's log.

## Tools: what the model may do

```tsx
/** Finds the patient's file by their full name and phone. Call it only once you have both. */
@tool({ stage: "identify", pii: ["name", "phone"] })
async findPatient(name: string, phone: string): Promise<Patient | null> {
  this.patient = await this.agenda().find(name, phone);
  if (this.patient) this.stage = "choose";
  return this.patient ?? null;
}
```

The docstring is what the model reads to choose the tool, joined into one line. The signature is
the schema it fills: `string`, `number`, `boolean` and arrays of them are typed; an interface or a
type declared in the same file is read field by field; an optional parameter is not required. What
the model sends is checked against it before the method runs.

| option | what it does |
|---|---|
| `stage` | visible while the state is in this stage, or one of these: `stage: ["choose", "book"]` |
| `when` | a question asked of the state on every change: `when: (s) => s.slots.length > 0` |
| `confirm` | the sentence said after the tool runs. **This is what makes a tool irreversible on the wire**; `{{result.x}}` names a field of what it returns |
| `announce` | what the agent says as the tool starts ("Let me check the agenda."), when the model's turn said nothing itself and wrote no line of its own in the argument `say` every tool carries; a turn that spoke first is not announced twice. No tool declares an argument named `say` |
| `quiet` | a move on the caller's screen, such as a pointer (TypeScript only for now): it runs as the model calls it, while the words of that answer still play, and the model is asked for no answer of its own. Without it, every tool's result is a turn the model answers |
| `preview` | how many items of a list the *model* sees. The state keeps every one |
| `pii` | the parameters that carry personal data: the log masks their values wherever the agent wrote them down (`state.changed`, `tool.result` and a line you log too), and `pinecall start` prints the log's version. A callback's number is what the callback is for, so `callback.requested` keeps it in the clear |
| `timeout` | how many seconds the platform waits for this method: 30 unless set, 300 at most |
| `params` | an explicit zod schema, when the signature is not enough: `import { z } from "@pinecall/agents"` |

A tool that throws does not crash the call: its message becomes the tool's result, marked as an
error, and the model reads it. Throw a sentence a model can use — "Tuesday has no free slots" —
never a stack trace. And ask the model for a word, not a record: `book(slot: string)`, looked up
among the slots it was offered, is safer than `book(slot: Slot)`.

## The hooks

```tsx
override async onCall(call: Call) {   // a call started; writes here are authored by the hook
  this.patient = await this.agenda().byPhone(call.from ?? "");
  if (this.patient) this.stage = "choose";
}

override onEnd(call: Call) {          // a line logged here still lands, though the call is over
  this.log("outcome", { stage: this.stage });
}

override onEvent(name: string, data: Record<string, unknown>, meta: EventMeta) {}   // an accepted outside fact
override onMemory(ops: MemoryOp[], call: Call) {}   // memory read or written: each op's `op` and `facts`
```

After `onEnd` the SDK sends `call.done`, and the gateway waits for it, up to three seconds, before it seals
the call: a log is closed to lines once sealed, so a line `onEnd` logs later than that is refused, and the
gateway's journal names it.

A hook that throws fails its call and no other: the call's log gets a `hook.failed` line naming the
hook (and the event, for `onEvent`) and the error, stderr one line, and the call goes on with what the
hook had written.

`onCall` runs before the first prompt goes out, so the model never reads a state the call was not
in; the state a golden or a persona opens the call in is applied after it, so the hook never
overwrites it. An outside fact reaches `onEvent` only if the class declared the pair in
`static events`: an event declared `from: ["app"]` that arrives from a browser is somebody else's
event with your name on it, and the hook never sees it.

### Before the first call: `static onServe`

A class can publish something for the pages that show it, once its agent is registered and before
any call: lines recorded in its own voice, which a page plays with no call, and a JSON document any
page reads with no key.

```ts
static override async onServe(serve: Serve) {
  const lines = await serve.record(["Welcome to Brightside.", "Pricing is simple."]);
  await serve.publish("welcome", { lines: lines.map(({ url, words }) => ({ url, words })) });
  serve.say(`welcome recorded · ${lines.length} lines`);
}
```

`record` answers each line's MP3 URL, its length and when each written word is said; a line the
agent recorded before, in the same voice, costs nothing, so `onServe` runs again on every reconnect
as it is. `publish` replaces the document under its name; a page reads it at
`GET /v1/agents/{slug}/public/{name}` with no key (`?env=sandbox` for the sandbox's), so put there only
what the page would show anyway. `say` writes one line in the terminal of whoever started the agent.
A throw is reported, and the agent serves its calls all the same.

## The call

Inside a tool, a hook or `render()`, `this.call` is the live call; outside one it throws.

```tsx
await this.say("One moment, let me check.");        // true once the turn lands, false after 30 s
await this.reply("Tell them it is booked.");        // the model speaks, guided by words nobody hears
this.call.send("cart", { total: 42 });              // a payload to the browsers in the room
this.call.participant(identity).mute();             // and .remove()
this.call.invite("+34910000001", { kind: "sip" });  // a phone leg into the call
await this.call.transfer("+34910000002");           // { ok, to, mode, error? }: ok false if they are still here
await this.call.attention("wants to talk to a person", { waitS: 60 });   // { ok, by, error? }
this.call.hold();                                   // and unhold()
this.call.dtmf("1#");
this.call.claim("4821");                            // the page showing 4821 follows this call
this.call.callback("+34600000001", { when: "tomorrow afternoon", note: "a quote" });
this.call.optOut("does not want more calls");       // their number joins the do-not-call list
this.call.hangup("done");
await this.knowledge.search("summer opening hours", { k: 3 });   // the chunks, searched for this call
```

`this.call` also carries `id`, `contact`, `from`, `channel`, `medium`, `today` — the day the call
runs in, which is what "next Tuesday" is counted from: the day a golden pinned when one did, else
the day the call opened — `history`, `room` and `claimed`.

There is no LiveKit here and no escape hatch to it: a need the room cannot express is a new
command with a name.

## The panel beside a conversation: `@view`

The console draws a pane beside every thread in **Calls**. A class that declares a view has its own
panel drawn there — the customer's file, their orders, the balance — from your own systems:

```tsx
import { Agent, view, type Who } from "@pinecall/agents";
import { Badge, Panel, Row, Rows, Stat, Table } from "@pinecall/agents/panels";

async function CustomerCard(who: Who) {
  const client = await crm.find(who.contact);
  if (client === undefined) return <Panel title="Not on file">Not in the CRM.</Panel>;
  return (
    <Panel title={client.name}>
      <Rows>
        <Row label="Since">{client.since}</Row>
        <Row label="Area">{client.area}</Row>
      </Rows>
      <Stat label="Jobs" value={client.jobs.length} />
      <Table columns={["date", "job", "amount"]} rows={client.jobs} />
      <Badge tone={client.debt > 0 ? "warn" : "good"}>{client.debt > 0 ? "owes" : "paid up"}</Badge>
    </Panel>
  );
}

@view(CustomerCard, "Customer")
export default class ClinicaNorte extends Agent {}
```

What reaches the console is a tree of the closed catalogue — `Panel`, `Rows`, `Row`, `Stat`,
`Table`, `Badge`, `Text` — drawn by the console's own parts; nothing a tenant writes reaches the
page's styling or its scripts. `who` is the conversation — `agent`, `contact`, `call` — and nothing
else: the panel is read beside threads that ended weeks ago, so it fetches what it shows. One per
class.

## What is refused when the class loads

Every one of these is refused before any call, with a message that says what to write:

| refused | the sentence |
|---|---|
| a tool with no docstring | `tool book: without a docstring no model can choose it; write a /** one line */ above the method` |
| a tool name a model cannot call | `a tool name is one word a model can call, not …` |
| `pii: ["dni"]` on a tool with no `dni` | `tool book: pii names parameters the tool has; unknown: dni` |
| `stage` on a class with no `stage` field | `tool book: stage names a value of this agent's own stage field, and ClinicaNorte declares none; add \`stage: Stages<"…"> = "…"\` to the class, or ask when(state) instead` |
| `@tool` on something that is not a method | `@tool goes on a method; … is not one` |
| a tool with an argument named `say`, which every tool carries for the model's own line | `bad_shape: tool echo: 'say' is the platform's argument, never a tool's own`, said by the gateway when `pinecall start` registers the agent |
| `@state({ pii: true, visibility: "public" })` | `two different answers to one question; write one` |
| both `@render(Prompt)` and a `render()` method | `ClinicaNorte declares both @render(Prompt) and a render() method; two ways to answer one question — keep one` |
| two `@view` decorators | `ClinicaNorte declares two views (…); a class draws one panel` |
| `language`, `greeting`, `says`, … as an instance field | `` `language` is the class's, not a call's state: declare it as static language = …`` |
| both `@llm(…)` and a `static llm` | `ClinicaNorte declares both @llm(…) and a static llm; keep one` |
| a judge file with no question, a bad `answer`, a `choice` with one choice, a `trigger` with no question | `offers.md: a judge asks a question of a call: write one below the front matter`, … |
| a persona file with no `goal` or `style`, or a key the wire does not know | `in-a-rush.json: a persona wants something: write its goal, in the first person` |
| `judges/` or `test/personas/` with files, and a class that declares neither | `agents/x/judges holds 2 judge(s) and the class declares none: static judges = judges({ on: ["consent", …] }) declares them, and which of Pinecall's run` |
