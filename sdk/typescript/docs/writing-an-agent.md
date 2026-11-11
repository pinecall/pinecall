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

Everything the agent **runs on** — the voice, the models, the language, the greeting, what it knows
by heart, what it remembers — is the class's. **An app written as code is set by its code and nothing
else**: the console's Setup shows what it runs on, read-only, and `pinecall agent set` and every other
verb that writes one agent's settings refuses an app, naming it. Change the class and deploy. A stage
the class leaves out runs on the org's default vendor for it and that vendor's default model; a field
left out reads as the runtime's default. The settings those verbs write belong to an agent built in
Studio, which has no code.

The stages are named in short, each a `static` like the rest of what the class declares:

```tsx
export default class FrontDesk extends Agent {
  static stt = "deepgram/flux";
  static llm = "google/gemini-3.5-flash-lite";
  static voice = "cartesia/f786b574-daa5-4673-aa0c-cbe3e8534c02";
  static judges = judges({ on: ["consent", "grounded"] });
  static timezone = "America/Los_Angeles";
}
```

A model is `"vendor/model"` or a vendor alone, and a voice is `"vendor/voice"`, the vendor and its own id
for the voice. A stage that takes options is written with them: `static llm = { model:
"openai/gpt-5.4-mini", temperature: 0.3 }`, `static stt = { model: "soniox/stt-rt-v3", endOfTurn:
"smart-turn" }`, `static voice = { voice: "cartesia/<id>", model: "sonic-2" }`. The decorators below say
the same thing above the class, and a class uses one of the two spellings for a stage, never both:

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

`static timezone = "America/Los_Angeles"` is the IANA zone the agent's day and clock are read in:
the model is told the date, the weekday and the hour there as the call opens, and `this.call.today`
is that day. Left out, the day is the gateway's own and the model is told no hour.

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
are refused too. A class that leaves the stage out runs it on the org's default vendor and that vendor's default model. The rest are `static` fields: an instance field is the call's state, so one of these
declared there is refused when the class loads.

| field | what it is | on the class |
|---|---|---|
| `voice` | the voice: its vendor and the vendor's id | `@voice("<vendor>", "<id>")` |
| `llm` | the model that answers, and its temperature | `@llm("<vendor>/<model>", { temperature })` |
| `realtime` | the model a voice call runs on alone, hearing and speaking itself | `@realtime("<vendor>/<model>", { options })` |
| `stt` | the ears, and who ends the caller's turn | `@stt("<vendor>/<model>", { endOfTurn })` |
| `judge` | the model its calls are judged on | `@judge("<vendor>/<model>", { options })` |
| `language` | the language the call is in | `static language = "es"` |
| `greeting` | how the call opens: the words, or the model's own | `static greeting = "…"` · `improvise` · `improvise("…")` |
| `hangup` | whether the model may end the call itself, and when, in your words | `static hangup = "…"` · `true` |
| `turn` | when the caller has finished, and may interrupt | `static turn = { endpointingMs: 300 }` |
| `says` | how a word the voice would misread is said | `static says = [{ word, spoken }]` |
| `hears` | the words the ears must know: names, brands, the doctor's surname | `static hears = ["…"]` |
| `memory` | what to remember about a caller across calls, and what never to | `static memory = { remember: […], forget: […] }` |
| `record` | whether the call is recorded | `static record = false` |
| `maxDuration` | the longest a voice call runs, in minutes, or `"off"` | `static maxDuration = 20` |
| `llmTimeout` | how long a turn waits for the model's first word, in seconds | `static llmTimeout = 8` |
| `silenceTimeout` | seconds of the caller saying nothing before a voice call ends, 5 to 3600 | `static silenceTimeout = 30` |
| `idle` | what it says when the caller goes quiet | `static idle = { says: ["Are you there?"], afterS: 7.5, times: 3 }` |
| `voicemail` | on a call it placed, the words left on a machine, or `true` to leave nothing | `static voicemail = "Please call us back."` |
| `sttFallbacks` · `ttsFallbacks` | who takes over when the vendor fails, in order | `static ttsFallbacks = ["cartesia"]` |
| `knowledge` | what the agent knows by heart: a page of Markdown, read whole on every call | `static knowledge = { path, text }` |
| `docs` | the base the agent searches per turn; declared, the folder `agents/<slug>/docs/` is pushed into it when the agent registers | `static docs = { base: "…", k: 4 }` |
| `bases` | several bases, in place of `docs`; each pushed on its own (`pinecall docs push --base`) | `static bases = [{ base: "faq" }, { base: "prices", k: 2 }]` |
| `monitors` | numbers of its calls it watches: each fires, once a day, on the agent's log and your webhook when it crosses its line | `static monitors = [{ name: "slow", metric: "e2e_median_s", above: true, threshold: 2 }]` |
| `hold` | the hold melody: a file beside the class and the wait before it, or silence | `static hold = { file: "hold.mp3", afterS: 1.5 }` · `"off"` |
| `widget` | how the widget presents the agent | `static widget = { title, tagline, greeting, accent, autostart, theme }` |
| `judges` | which of Pinecall's judges its calls meet, and its own | `static judges = judges({ on: ["consent", …], own: [offersNextSlot] })` |
| `personas` | which of Pinecall's callers its simulations play, and its own | `static personas = personas({ on: ["in-a-hurry", …], own: [hurried] })` |

**The judges and the callers are the class's the same way, and they are code.** `judges({ on, own })`
names which of Pinecall's judges the agent's calls meet (`on`, every other off) and the agent's own
(`own`), each an `ownJudge({ name, asks, answer, choices, when, trigger, reads })`: the question
the judge model answers about a finished call, and how and when. `personas({ on, own })` is the
same for the callers `pinecall simulate` plays, each of its own an `ownPersona({ name, goal, style,
about, facts, expects, behavior, … })`, what `PUT …/personas/{name}` takes. `pinecall new` writes
them in `agents/<slug>/harness.ts`, one file for both, imported by the class:

```ts
// agents/front-desk/harness.ts
import { ownJudge, ownPersona } from "@pinecall/agents";

export const offersNextSlot = ownJudge({ name: "offers-next-slot", asks: "Did the agent offer the next free slot before the caller asked twice?", reads: ["facts"] });
export const hurried = ownPersona({ name: "hurried", goal: "leave a message: the delivery has to come after 4 pm", style: "short sentences, interrupts", expects: ["The agent should write the message down."], behavior: { interrupts: 0.3, pauseS: 1 } });
```

A wrong one is refused when the class loads, by a sentence that names it (`offers-next-slot: a
judge that answers one of several needs at least two choices`), and so are two of one name.
Declared, the class is the agent's list: the console shows both locked, "set by the class", and
`pinecall judges add` or `personas add` is refused naming the class; `pinecall judges pull`,
`personas pull` and `personas generate --save` write code into that file instead. A class that
declares neither leaves both to the console and the CLI, as before. The org's own judges
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
| `delayed` | what the agent says when the wait has grown long, 5 seconds in unless `delayedAfter` says otherwise; `failed`, what it says when the tool failed, before the model reads why |
| `quiet` | a move on the caller's screen, such as a pointer: it runs as the model calls it, while the words of that answer still play, and the model is asked for no answer of its own. Without it, every tool's result is a turn the model answers |
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

## The voice app: the project's lines

A project may have an `app.ts` beside `agents/`: its voice app. It says which agent answers each of
the project's numbers, the words a call on that line opens with, and what every agent of the app
says to a caller who went quiet. It is optional: an agent alone answers its number as before.

```ts
// app.ts
import { voiceApp } from "@pinecall/agents";
import FrontDesk from "./agents/front-desk/agent";

const app = voiceApp("brightside", { timezone: "America/Los_Angeles" });

app.line("+1 415 555 0134", { answers: FrontDesk, greeting: "Brightside Dental. How can I help?" });
app.silence({ after: "8s", say: "Are you still there?", times: 2 });

export default app;
```

`timezone` is the zone every agent of the app reads its day and its clock in, the same setting as a
class's `static timezone`. `pinecall start` finds the file at the project's root and serves the agents with it; a save of it
reloads them. `app.line(number, FrontDesk)` is the short form, with no greeting. The greeting is said
as written, by the agent, before any model runs: it is that agent's `greeting`, declared by the app,
and `silence` is its `idle`. A class that declares `static greeting` or `static idle` itself and gets
one from the app too is refused when the app loads, naming both, since a call runs on one of them.

### What the app hears

```ts
app.on("visit.booked", async (call, visit) => {
  await reminders.schedule(visit);
});

app.on("call.ended", async (call, ended) => {
  await db.calls.insert({ call: call.id, agent: call.agent, reason: ended["reason"] });
});
```

`app.on(name, handler)` runs the handler on every entry of that name on a call of the app's agents.
The name is an entry of the call's log by its type (`call.started`, `call.ended`, `call.score`, `handoff`
for a pass and `routed` for a line's choice), or a line an agent logs by its own name:
`this.log("visit.booked", visit)` in a tool is what the first handler above hears. The handler is
told the call (`id`, `agent`) and what the entry carries. One that throws is said in the terminal,
and the others run. The handlers run in the process that serves the agents: what happens while it is
down is not heard later.

### A rule every agent keeps

```ts
app.rule("Never quote a price that is not in the price list.");
```

A rule is read into the prompt of every agent of the app, and a judge asks of each call whether it
was kept: the call's score says so, as it does for the judges a class declares. The judges are named
`app-rule-1`, `app-rule-2`, in the order the rules are written. An agent's declared judges are its
whole list, so an app with rules owns the list of each of its agents: name the ones of Pinecall's you
want beside them in the class, `static judges = judges({ on: ["grounded"] })`.

### A team: the call passed from one agent to another

A line may name a team, the agents its call can pass to. Each says what it takes, in the words a
model reads to choose it:

```ts
// agents/billing/agent.tsx
/** You handle charges, invoices and refunds for Brightside Dental. */
export default class Billing extends Agent {
  static takes = "a question about a charge, an invoice or a refund";
}
```

```ts
app.line("+1 415 555 0134", { answers: FrontDesk, greeting: "Brightside Dental. How can I help?", team: [Billing] });
```

The agent on the call is offered one tool per teammate, named by its class (`transfer_to_billing` for
`Billing`), and the model calls it
when the caller asks for that; a caller who only says hello is passed to nobody. A tool can pass the
call itself, with what the next agent should know:

```ts
/** The caller disputes a charge and names the invoice. */
@tool()
disputeCharge(invoice: string) {
  return this.call.handoff(Billing, { invoice });
}
```

From the pass on, the call is the teammate's: its instructions, its tools, its state, and its `onCall`,
where `this.call.handed` is what it was handed. `this.call.shared` is an object the agents of one call
share: what the first one wrote there, the next one reads. The conversation so far stays with the call,
and the pass is a `handoff` line on its log. A call is passed three times at most; the fourth is
refused and the agent answers itself.

Two things to know. The agents of a team give each tool a name of its own, or the app is refused
when it loads. And the call keeps the voice and the models of the agent that answered it: the gateway
still knows the call by that agent, which is also where it is listed and judged.

### A line that chooses who answers

`answers` may be a function. It runs as the call comes in, while the caller hears the greeting, and
returns the agent of the team that serves this call:

```ts
app.line("+1 415 555 0134", {
  greeting: "Brightside Dental. How can I help?",
  answers: async (call) => {
    if (clinic.isClosed(call.today)) {
      return AfterHours;
    }
    return FrontDesk;
  },
  fallback: FrontDesk,
  team: [AfterHours, Billing],
});
```

`fallback` is the agent the number is pointed at. It answers when the function returns nothing,
throws, takes more than a second, or names an agent that is not of the line's team; then the call's
log has a `routed` line saying why. The function is handed the call as a hook is: `id`, `contact`,
`from`, `to`, `channel`, `today`, and what the call was opened with.

The number stays your org's: `pinecall numbers` points it at the agent. A line whose number the
gateway does not route to its agent is said once in the terminal, and the agent serves its other
calls all the same. An agent that answers two lines opens both with the same greeting, or with none.

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

`this.call.instruction` is what this call is for, when whoever placed it said so: a dial's `instruction`
(`pinecall dial reminder +1415… --instruction "Remind Ana of her cleaning tomorrow."`). The prompt carries
it for the whole call, so the class does nothing with it unless it wants to.

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
| an `ownJudge` with no `asks`, a bad `answer`, a `choice` with one choice, a `trigger` with no question | `offers: a judge asks a question of a call: write it as asks`, `offers: a judge that answers one of several needs at least two choices`, … |
| an `ownPersona` with no `goal` or `style`, or a key the wire does not know | `in-a-rush: a persona wants something: write its goal, in the first person` |
| two judges or two personas of one name in `own` | `two judges called offers-next-slot: a name is declared once` |
