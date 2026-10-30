# Writing an agent

An agent is one Ruby class. Everything the model can see about it comes from four places: the
comment above the class, what the class declares, the comments above its tools, and the view.

```ruby
require "pinecall"

# You are the front desk of Clínica Norte. Formal, short sentences.
# Everything you say is read aloud: no lists, no markdown.
class ClinicaNorte < Pinecall::Agent
end
```

That comment is the `identity` block of the prompt — the first of the static blocks, which never
change during a call and are what a provider caches. Write it as instructions to a person, not as
documentation.

For a class with no source file to read (one built at runtime, one loaded from a database), say it
out loud instead: `doc "You are the front desk…"`.

## Config: what the agent *is*

Declared on the class, because it is not something the agent remembers. It never changes during a
call and no view renders it.

```ruby
channel_rules false       # leave out the <channel> block: how to write for a voice, a website, WhatsApp
slug "front-desk"         # the name it registers as; left out, the folder's name under `pinecall start`
accepts "slot.released", from: %i[app]   # the outside events it takes, and from whom
```

A class served under another slug than its folder's is refused. The framework's rules are English
and tell the model to answer in the caller's language; the language the call is in is the
environment's, below.

**The doors are not here.** A number is bought, pointed at an agent and moved by whoever answers
the telephone, not by whoever deploys: it is a row the org keeps — `pinecall numbers import
<+34…> --agent <slug>`, or the console's Numbers screen. And the web needs no door at all: every
agent can be talked to from a page. A class that still writes `phone "+34…"`, `whatsapp` or
`web true` still loads, and is writing something nobody reads.

### The environment: the settings', or the class's

Everything the agent **runs on** is its settings': set per world and per corner, versioned, with who
set it and why, and changed without a deploy — by `pinecall agent set`, the console's Configure
screen, or the verb the table names. Those verbs belong to the one Node CLI (`pinecall` on npm);
this gem ships no executable. The class may declare any of them instead, as a class macro, and
**what the class declares wins**: the settings of that field are not read for the agent, the console
shows it locked, "set by the class", and a `pinecall agent set` of it is refused naming the class.
Take the macro out and deploy, and the settings apply again.

```ruby
# Recepción de Clínica Norte: da, cambia y cancela turnos.
class ClinicaNorte < Pinecall::Agent
  voice "cartesia", "a0e99841-438c-4a64-b679-ae501e7d6091", model: "sonic-2"
  llm "openai/gpt-5.4-mini", temperature: 0.3, builds: "responses.LLM", options: { use_websocket: true }
  stt "soniox/stt-rt-v3", end_of_turn: :smart_turn
  judge "openai/qwen3-32b", options: { base_url: "http://gpu:8000/v1" }
  language "es"
  greeting "Clínica Norte, buenas, ¿en qué le ayudo?"
  hangup "the caller says goodbye or needs nothing else"
end
```

`greeting` is the words, said as written — instant, and no model runs — or the model's own:
`greeting :improvise` opens on the prompt alone, `greeting improvise("Saludá por el nombre si lo
sabés")` with an instruction for the opening. The caller cannot cut it short unless it says so:
`greeting "…", interruptible: true`, or `improvise("…", interruptible: true)`. `hangup` is when the
model may end the call, in your words, or `hangup true` whenever it judges the call done. `stt`
also takes `end_of_turn:`, who says the caller's turn is over: `:stt` the ears themselves (Deepgram
Flux; refused for ears that cannot), `:livekit` or `:smart_turn` (Smart Turn v3), a model on the
worker that runs on any key. Left out, the ears end the turn where they can and Smart Turn v3 does everywhere else.

`llm` and `stt` take `vendor/model` or a vendor alone; `voice` the vendor and its own id for the
voice, and refuses one without the id at load. Each takes `builds:`, a class of the vendor's LiveKit
plugin other than its default (a dot reaches into a module of it: `responses.LLM` is OpenAI's
Responses API, and `use_websocket` its WebSocket), and `options:`, that class's keyword arguments as
the plugin names them, passed as given and over Pinecall's. **Both run only on your org's own key
for that vendor**: on a key Pinecall lends they are refused when the agent registers, naming
`pinecall providers add <vendor>`, since an option can point the plugin at another server. `llm`
also takes `temperature:`, which runs on any key. A model that hears and speaks itself is not an
`llm`: `realtime "xai/grok-voice-3.0", options: { voice: "eve" }` runs the agent's voice calls —
phone and web — on it alone, with no ears and its own voice, while the `llm` keeps answering the
written ones; `pinecall providers` lists the vendors' realtime models, its options run on your org's
own key alone, and an `llm` that names such a model is refused at registration. A realtime model that says given words itself (xAI's Grok does) is the call's only voice: the recording notice, a greeting given as words and a confirmation's read-back are said by it, in its own voice; one that cannot leaves them to the agent's voice, and the call then has two. A vendor that is not installed, or
does not do the stage, is refused at registration. `llm` fixes the whole model: with it in the class,
`--temperature`, `--llm-builds` and `--llm-option` are refused too.

`judge` is the model the agent's calls are judged on at hang-up, over the org's choice and
Pinecall's own: `vendor/model` or a vendor alone, with `builds:` and `options:` as `llm` takes them.
On a key of your org's own for that vendor — a local model's server among them, through
`options: { base_url: "…" }` — its evals are never billed; on a key Pinecall lends they are. The
judge is asked for a forced tool call, so a local model must call tools.

| field | what it is | on the class | or in the settings |
|---|---|---|---|
| `voice` | the voice: its vendor and the vendor's id | `voice "<vendor>", "<id>", model: "…"` | `pinecall agent set --voice` |
| `llm` | the model that answers, and its temperature | `llm "<vendor>/<model>", temperature: 0.3` | `pinecall agent set --llm` |
| `realtime` | the model a voice call runs on alone, hearing and speaking itself | `realtime "<vendor>/<model>", options: { … }` | `pinecall agent set --realtime` |
| `stt` | the ears, and who ends the caller's turn | `stt "<vendor>/<model>", end_of_turn: :smart_turn` | `pinecall agent set --stt` · `--end-of-turn` |
| `judge` | the model the calls are judged on; on your own key its evals are not billed | `judge "<vendor>/<model>", options: { base_url: "…" }` | the settings' `judge`, `judge_builds`, `judge_options` |
| `language` | the language the call is in | `language "es"` | `pinecall agent set --language` |
| `greeting` | how the call opens: the words, or the model's own | `greeting "…"` · `greeting :improvise` · `greeting improvise("…")` | `pinecall agent set --greeting '…'` · `--greeting improvise` · `--greeting improvise:'…'` |
| `hangup` | whether the model may end the call itself, and when, in your words | `hangup "…"` · `hangup true` | `pinecall agent set --hangup '…'` · `--hangup any` |
| `turn` | when the caller has finished, and may interrupt | `turn endpointing_ms: 300` | `pinecall agent set --endpointing-ms` |
| `says` | how a word the voice would misread is said | `says [{ word: "DKV", spoken: "de ka uve" }]` | `pinecall lexicon add <word> --say '…'` |
| `hears` | the words the ears must know: names, brands, the doctor's surname | `hears "Vidal", "Sanitas"` | `pinecall lexicon hear <word> …` |
| `memory` | what to remember about a caller across calls, and what never to | `memory remember: […], forget: […]` | `pinecall memory policy --remember '…' --forget '…'` |
| `record` | whether the call is recorded | `record false` | `pinecall agent set --record on\|off` |
| `max_duration` | the longest a voice call runs, in minutes, or `:off` | `max_duration 20` | `pinecall agent set --max-duration 20` |
| `llm_timeout` | how long a turn waits for the model's first word, in seconds | `llm_timeout 8` | `pinecall agent set --llm-timeout 8` |
| `knowledge` | what the agent knows by heart: a page of Markdown, read whole on every call | `knowledge path: "knowledge.md", text: File.read(…)` | `pinecall agent knowledge edit` |
| `docs` | the base the agent searches per turn, and how many chunks a turn reads; declared, the folder `agents/<slug>/docs/` is pushed into it when the agent registers | `docs base: "clinica-norte", k: 4` | `pinecall docs push`, then `pinecall docs attach <base>` |
| `judges` | which of Pinecall's judges its calls meet, and its own | `judges on: %w[consent grounded]`, its own as `judges/<name>.md` | `pinecall judges on\|off\|add` |
| `personas` | which of Pinecall's callers its simulations play, and its own | `personas on: %w[in-a-hurry]`, its own as `test/personas/<name>.json` | `pinecall personas on\|off\|add` |

Called with no argument, each macro reads what the class (or its parent) declared.

**The judges and the callers are the class's the same way.** `judges on: [...]` names which of
Pinecall's judges the agent's calls meet, every other off, and the agent's own judges are the files
under `agents/<slug>/judges/`, one each, in the library's own format: front matter (`answer`,
`choices`, `when`, `trigger`, `reads`) and the question below it, the file's name the judge's.
`personas on: [...]` is the same for the callers `pinecall simulate` plays, the agent's own under
`agents/<slug>/test/personas/`, one JSON file each, what `PUT …/personas/{name}` takes. The folders
are read beside the class's own file when the agent registers. Declared, the class is the agent's
list: the console shows both locked, "set by the class", and `pinecall judges add` or
`personas add` is refused naming the class; a class that declares neither leaves both to the console
and the CLI, as before. A folder with files beside a class that declares nothing is refused when
the agent registers, saying what to write. The org's own judges (`pinecall judges add --org`) meet
every agent's calls either way.

Mid-call, `say "..."` and `reply "..."` are still methods of the class, for when something happens
that the caller should hear now; how the call *opens* is `greeting`, the class's or the settings'.

### What it knows, what it reads, what it remembers

Each of the three is a setting unless the class declares it (`knowledge`, `docs`, `memory` above),
and the runtime does the work for all of them:

- **What it knows by heart** — the hours, the prices — is a page of Markdown. The gateway writes it,
  whole, into the `knowledge` block of the prompt, once per call, in the cached prefix. A class that
  does not declare it sends nothing for that block, so `pinecall prompt` prints it empty.
- **What it searches** is a base: a folder of Markdown pushed to the gateway and attached to the
  agent. The platform's `search` tool runs it and the chunks reach the model as a **tool result**.
- **What it remembers** about a contact is the memory policy, in its own words; the platform's
  `recall` tool answers from it, the same way, and at hang-up one model call writes what this call
  taught.

**Neither a fact nor a chunk ever reaches the prompt.** Both arrive as a `tool_result`, JSON, in
the history, where a model reads them as information rather than as an instruction — the rule, and
the vendor guidance behind it, is `runtime/docs/security/prompt-injection.md`. What the view may do
with memory is ask it a question: `remembers?("usual doctor")`, and then say a sentence of your
own. The history of a contact, and the right to be forgotten, are `pinecall memory CONTACT` and
`pinecall memory forget CONTACT`.

## State: what it remembers

```ruby
stage :identify, :choose, :book, :done   # declares the stage field and its only values
state :patient, visibility: :pii
state :slots, []                          # every call gets a list of its own
state :proposed
state(:identified) { !patient.nil? }      # derived: read like any field, assigned by nobody
```

**Tools are the only writers.** Assigning a field anywhere else raises `UnauthoredWrite`:

```ruby
agent.patient = row
# => state field patient was assigned outside a tool and outside a lifecycle hook;
#    tools are the only writers of state
```

The author of a write is the tool's own name, and it rides `Fiber[]` rather than a global — so two
calls being served at the same moment never read each other's. The log says it: each write is one
`state.changed` entry whose `cause` names the tool and the model's id for its call, the outside fact
that `on_event` was handling, or the hook (`on_call`, `on_memory`).

`visibility:` is `:public`, `:tenant` (the default, and the wire's) or `:pii`.

## Tools: what the model may do

```ruby
# Finds the patient by name and phone. Ask for both before calling it.
tool stage: :identify, pii: %i[name phone]
def find_patient(name:, phone:)
  self.patient = Agenda.find(name, phone)
  self.stage = :choose if patient
  patient
end
```

`tool` marks the method **defined next** — the same hook Sorbet's `sig` uses — so the comment
stays where a person would write it anyway. That comment is what the model reads to choose the
tool; the signature is the schema it fills.

| option | what it does |
|---|---|
| `stage:` | visible while the state is in one of these stages. Sugar over `when:` |
| `when:` | a question asked of the state, on every change: `-> { slots.any? }` or `->(s) { s.slots.any? }` |
| `confirm:` | the sentence said after the tool runs. **This is what makes a tool irreversible on the wire**; `{{result.x}}` names a field of what it returns |
| `announce:` | what the agent says as the tool starts ("Let me check the agenda."), when the model's turn said nothing itself and wrote no line of its own in the argument `say` every tool carries; a turn that spoke first is not announced twice. No tool declares an argument named `say` |
| `preview:` | how many rows of a list result the *model* sees. The state field keeps every row |
| `pii:` | parameters that carry personal data: masked in the call's log by declaration, and by value wherever the agent writes them down, as in what `pinecall start` prints |
| `timeout:` | how long the platform waits for this method, in seconds |
| `params:` | the type of a parameter when a bare name is not enough |
| `doc:` | the description, for a class with no source to read |

**A tool takes keyword arguments and nothing else.** A model fills a JSON object by name; filling
by position is a thing only a human gets right, so a positional argument is refused at load.

**Types come from `params:`.** A Ruby signature carries none, so a parameter nobody typed is
`string` — which is what a person on the phone says. Anything else says so once:

```ruby
tool params: { day: String, how_many: Integer, slot: { type: "object" } }
def free_slots(day:, how_many: 3, slot: nil)
```

**What a class sends is JSON.** What a tool returns is what the model reads, and a state field and a
logged line go to the call's log the same way. A hash, an array, text or a number goes as it is; a
`Data` or a `Struct` — alone, or inside an array or a hash — goes as its fields, so a tool that returns
`knowledge.search(…)` hands the model `{ path, heading, text }` for each hit.

## What is refused, at load

Every one of these raises `DeclarationRefused` when the file is loaded — never in the middle of a
call, and never as a gateway's refusal of the socket:

| refused | the sentence |
|---|---|
| a tool with no comment above it | `without a docstring no model can choose it` |
| `def book(chosen)` | `a model fills a JSON object by name, so a tool takes keyword arguments` |
| `pii: %i[dni]` on a tool with no `dni:` | `pii names parameters the tool has; unknown: dni` |
| `stage: :pay` where `stage` has no `:pay` | `pay is not one of this agent's stages (identify, book)` |
| `stage:` on a class with no `stage` | `…declares none; add \`stage :identify, :book\`` |
| `state :cart` twice | `declares cart twice` |
| `voice "carolina"` (no voice id) | `a voice the class declares names its vendor and the voice: voice "<vendor>", "<voice id>"` |
| `tool retries: 3` (an option `tool` does not take) | `tool takes no retries` |
| two `panel` blocks | `… declares two panels (One and Two); a class draws one panel` |
| `panel` with no block | `panel takes the block that draws it` |
| `greeting 42`, `hangup 42`, `stage` with no names, a tool named `open?`, a tool taking `**anything` | a sentence naming what it takes |
| a judge file with no question, a bad `answer`, a `choice` with one choice, a `trigger` with no question | `offers.md: a judge asks a question of a call: write one below the front matter`, … |
| a persona file with no `goal` or `style`, or a key the wire does not know | `in-a-rush.json: a persona wants something: write its goal, in the first person` |
| `judges/` or `test/personas/` with files, and a class that declares neither | `agents/x/judges holds 2 judge(s) and the class declares none: judges on: ["consent", …] declares them, and which of Pinecall's run` |

Through `pinecall start` or `pinecall prompt` the sentence is printed alone, and the verb exits 2.

A view is the one thing read later, at render: a field the class never declared raises there, by
name, the same way an undefined instance variable does in a Rails view. A view that raises fails its
own call and nothing else: the call's log gets a `render.failed` entry with the exception's class and
message, the model keeps the view it had, and every other call carries on. A hook that raises
(`on_call`, `on_event`, `on_memory`, `on_end`) fails the same way: a `hook.failed` entry names the hook
(and the event, for `on_event`), the call goes on with what the hook wrote before it raised, and an
`on_end` that raises still closes the log and says `call.done`.

## The hooks

```ruby
def on_call(call)                  # a call started. Writes here are authored by the hook
  self.patient = Agenda.by_phone(call.from)
  self.stage = :choose if patient
end

def on_end(call)  = log("outcome", { stage: })
def on_event(name, data, meta)     # an outside fact this class declared with `accepts`
def on_memory(ops, call)           # memory read or written: each op's :op and :facts
```

`on_call` runs before the first render, so the model never reads a state the call was not in. After
`on_end` the bridge sends `call.done`, and the gateway waits for it, up to three seconds, before it seals
the call: a log is closed to lines once sealed, so a line `on_end` logs later than that is refused, and
the gateway's journal names it.

An outside fact only reaches `on_event` if the class declared the pair:

```ruby
accepts "agenda.changed", from: %i[app]
```

An event declared `from: [:app]` that arrives from a browser is somebody else's event with your
name on it, and the hook never sees it.

## The call

Inside a tool or a hook, `call` is the live call:

```ruby
say "One moment, let me check."        # blocks until the turn lands, or 30 seconds
reply "Tell them it is booked."        # the model speaks, guided by words nobody hears
call.send_to("cart", { total: 42 })     # a payload in the browser
call.participant(id).mute
call.invite("+34910000001", kind: :sip)   # a phone leg; kind: :participant for a seat
call.transfer("+34910000002")           # blocks until the log says how it went: a Transferred
call.attention("wants to talk to a person", wait_s: 60)   # an Attended: who took the line
call.hold                               # and call.unhold
call.dtmf("1#")
call.claim("4821")                      # the page showing 4821 follows this call; call.claimed says so
call.callback("+34600000001", at: "tomorrow afternoon", note: "a quote")
call.opt_out("does not want more calls")  # their number joins the org's do-not-call list
call.hangup("done")
log "outcome", { reference: booking[:reference] }
knowledge.search("summer opening hours", k: 3)   # the bases attached to the agent, searched for this call
```

What the call is, on the line that carries it:

```ruby
call.id  call.from  call.to  call.channel  call.medium  call.today
call.direction    # "inbound" when the public reached the agent, "outbound" when the agent dialled
call.caller       # who the platform knows is on the line: { id:, name:, phone:, email: }, nil when nobody is named
call.metadata     # what the call was opened with, such as a token's metadata: {} when none
```

`transfer` and `attention` block the tool that called them until the log answers — `ok: false`
and a sentence when nobody did, or when the call ended first. `knowledge.search` (or
`call.search`) asks the gateway, which searches the bases attached to the agent and logs what it
found, and answers an array of `Pinecall::CallWorld::Found` — `path`, `heading` and `text` each;
a class that searches says so when it registers, so a world with no base attached is refused
then and not mid-call. A view can ask `call[:claimed]` for the page code this call claimed.

There is no LiveKit here and no escape hatch to it: a need the room cannot express is a new
command with a name.

## The panel beside a conversation: `panel`

The console draws a pane beside every thread in **Calls**. Without a panel it is what the console
itself knows — how many conversations there have been with this person, what they came in by, how
long the agent spent on the line with them. A class that declares a panel has **its own drawn over
that**, and that is where the business's data goes: the customer's file, their orders, the balance.

```ruby
class ClinicaNorte < Pinecall::Agent
  def self.crm = Crm.new(ENV.fetch("CRM_URL"))

  panel "Customer" do |who|
    client = crm.find(who.contact)
    next panel("Not on file") { text "Not in the CRM." } if client.nil?

    panel client.name do
      rows do
        row "Since", client.since
        row "Area", client.area
      end
      stat "Jobs", client.jobs.length
      table columns: %w[date job amount], rows: client.jobs
      badge client.debt.positive? ? "owes" : "paid up", tone: client.debt.positive? ? :warn : :good
    end
  end
end
```

It is the TypeScript package's `@view`, and what reaches the console is the same: a tree of the
closed catalogue — `panel`, `rows`, `row`, `stat`, `table`, `badge`, `text` — drawn by the console's
own parts, in the theme the person reading chose; nothing a tenant writes reaches the page's
styling, its scripts or its key. `who` is the conversation — `agent`, `contact`, `call` — and nothing
else: the panel is read beside threads that ended weeks ago, so it fetches what it shows. It runs in
your process, under `pinecall start`; a method the block calls that is not one of the catalogue's is
the class's own (`crm` above). The gateway is told only the panel's name when the class registers;
a panel that raises is said in the pane, in its own words, and the conversation's screen keeps
working. One per class, and a subclass does not inherit it.
