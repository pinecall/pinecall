# Testing an agent

Ring 0 is the ring your own suite lives in: no network, no key, no model, no gateway. It is the
one that runs on every commit, in a second, and it is where nearly every mistake is caught.

```ruby
require "minitest/autorun"
require "pinecall"
require "pinecall/testing"
require_relative "../agent"

class ClinicaTest < Minitest::Test
  def setup
    @gateway = Pinecall::Testing::Gateway.new
    @mounted = Pinecall.mount(ClinicaNorte, client: @gateway)
  end

  def test_a_patient_on_file_is_not_asked_for_their_name_again
    call = @gateway.call_started(from: "+34600123456")

    assert_includes call.prompt, "You are talking to Marta Ruiz"
    assert_equal %w[free_slots], call.tools
  end
end
```

`Pinecall::Testing::Gateway` is a gateway that is not there. It answers the two declarations, keeps
every command the agent sent, and lets the test say what happened next.

## Driving a call

| you write | what happens |
|---|---|
| `gateway.call_started(from:, channel:, id:, state:)` | a call opens, `on_call` runs, then `state:` (what `call.started` carries when a golden or a persona opened it) is written over the hook's, and the first prompt goes out. Returns the handle |
| `call.tool("free_slots", day: "Tuesday")` | the model calls a tool. Returns the `tool.result` the agent sent back |
| `call.said("Tuesday works for me")` | the caller said something |
| `call.fact("agenda.changed", { slots: [] })` | a fact from the tenant's backend. `from: "participant"` for a browser |
| `call.ended` | the call is over, `on_end` runs |
| `gateway.call_attached(state:, id:)` | a call handed over mid-conversation: no `on_call`, the state the gateway kept, the whole prompt sent |
| `gateway.finds({ path:, heading:, text: }, …)` | what every search answers with; `gateway.searched` is what was asked, `{ call:, query:, k: }` each |

## Asking what the agent said

| you read | what it is |
|---|---|
| `call.prompt` | the `view` block as the agent last sent it: the last thing the model reads |
| `call.block("knowledge")` | any of the four blocks as the agent last sent it, by name. `nil` until it had something to say |
| `call.tools` | the tools the model may call right now, by name |
| `call.state` | the state as the agent last said it |
| `call.commands` | everything said on this call, in order |
| `call.last("call.log")` | the last command of one type |
| `@mounted.serving(call.id)` | the instance itself, for an assertion about a field |

## What is worth a test

The things a prompt makes true, not the things a method returns:

```ruby
def test_a_phone_call_offers_two_slots
  by_phone = @gateway.call_started(id: "CA_tel", from: "+34600123456", channel: "phone")
  by_phone.tool("free_slots", day: "Tuesday")

  assert_includes by_phone.prompt, "Offer at most two"
end

def test_a_slot_nobody_offered_is_refused_instead_of_booked
  call = @gateway.call_started(from: "+34600123456")
  call.tool("free_slots", day: "Tuesday")

  assert_includes call.tool("propose", chosen: "Sunday")[:error], "is not one of the slots"
end

def test_booking_is_irreversible_so_it_is_read_back
  spec = @mounted.options[:tools].find { |one| one[:name] == "book" }

  assert_equal "irreversible", spec[:side_effect]
end
```

A tool that raises is not a broken test: the model is waiting for an answer and reads the message
as the tool's own result, so `call.tool(...)` gives you back `{ error: "…" }` and the call carries
on. That is what you assert on.

## Without mounting anything

The prompt is a pure function of the state, so most assertions need no gateway at all:

```ruby
agent = ClinicaNorte.new.seal
agent.start_in(stage: :book, slots: [slot])

assert_includes Pinecall.render(agent)[:view], "Tuesday at ten"
```

`start_in` writes the fields a case names over the ones the class gave itself. `restore` is the
other door and means something stronger: a whole state, so a field it leaves out is cleared.

## The rings above

The verbs are the one `pinecall` CLI's (npm), the same for a Ruby project as for a TypeScript
one, in the same layout: `agents/<slug>/agent.rb`, `agents/<slug>/test/goldens/`, `agents/<slug>/test/memory/`,
`agents/<slug>/docs/`. Only `pinecall start` and `pinecall prompt` start this gem's serve entry; the
others start nothing and reach whoever holds the agent.

| ring | what it asks | how |
|---|---|---|
| 1 | does the agent hold its goldens? | `pinecall test` — the goldens under `agents/<slug>/test/goldens/`, played on whoever holds the agent: your `pinecall start`, or production's with `--prod` |
| 2 | does it hold on a real line? | `pinecall test --voice` · `pinecall simulate --voice` |
| 3 | what does one real call score? | `pinecall eval <call-id>` |
| 4 | what did every call score? | `call.score`, written by the runtime at hang-up |

## The index has a golden of its own

The rings test the agent. None of them tests the **index**, and they cannot: a ring watches a
conversation, so it only ever sees the passage retrieval handed over. Whether a better one existed
and was missed is a question no conversation can answer, because the model never saw the one it
missed.

That is what a knowledge golden is for. One file beside the documents it asks about — a question,
and the chunk that should answer it:

```json
[
  { "asks": "how much is my co-payment?",
    "expects": "insurance.md › Insurance and billing › Co-payments" },
  { "asks": "do I have to fast before the blood test?",
    "expects": "test-preparation.md › Preparing for a test › Blood tests" }
]
```

`expects` is the heading path a chunk carries, which is what you can read off your own documents:
naming a file alone accepts any chunk of it, naming a heading accepts that section and what is
under it. Fifty to a hundred questions per base is the size that stops being noise.

```bash
pinecall docs eval                             # agents/<slug>/test/goldens/docs.json
pinecall docs eval --k 4                       # as many chunks as the agent's attachment asks for
pinecall docs eval golden.json --base clinica-norte
```

```
clinica-norte · pplx-embed-context-v1-0.6b · 7 questions · recall@4 1.00 · nDCG@10 0.89 · 918 ms
```

| figure | means |
|---|---|
| `recall@k` | the share of questions whose chunk came back at all. **The one that matters**: a chunk the model never sees cannot be used, whatever its rank |
| `nDCG@10` | how high it ranked, discounted logarithmically. Two indexes that both find a passage are not equal if one puts it first and the other seventh, because `k` cuts |
| the model named | the embedder that wrote the vectors. Two scores are comparable only under one model |

Every question it missed is printed with what came back instead, and the verb **exits 1** when
anything did — so a base belongs in CI beside `rake test`. Both figures are computed by code, with
no model in the loop, so two runs over one base answer the same numbers.

A golden is fixed and the index is the variable. **A question is never softened so a change can
pass.** What you change instead is the documents, the chunking, `k`, `min_score`, or the embedder.

## Memory has a golden of its own, and it is the write side

The ring-1 goldens above ask whether the agent USES what it remembered. Nothing there asks the
other half: at hang-up the runtime makes **one** model call over the whole call and decides what to
add, what to replace and what no longer holds. That call is the half that persists, and it can fail
in four ways that all cost a business:

| failure | what it does |
|---|---|
| misses what mattered | the next call asks the same question again |
| invents a fact | the agent asserts something the caller never said, forever |
| does not supersede | "prefers mornings" and "prefers afternoons" both live, and the model picks |
| writes a `forget` category | you listed `payments` as never-keep, and there it is |

An extraction golden is one call **already held** — both speakers, because nothing is re-run — the
facts memory already holds about that caller, and what must come of it. One file per case, in
`agents/<slug>/test/memory/` of the project:

```json
{
  "name": "keeps the allergy and never the card",
  "said": [["caller", "I'm Marta, I'm allergic to penicillin"],
           ["agent",  "Noted. Does Tuesday work for you?"],
           ["caller", "Yes. And here's my Visa, 4242 4242 4242 4242"]],
  "holds": [],
  "expect": { "writes": ["allergies"], "never": ["payments"], "never_says": ["4242 4242 4242 4242"] }
}
```

| field | means |
|---|---|
| `said` | the call as it happened, `["caller" \| "agent", "…"]` per line. Both speakers: this is a conversation already held, handed to the hang-up's one model call |
| `holds` | what memory already holds about this caller. They are shown to the model with ids, and nothing is written to or read from the memory table |
| `plants` | sentences somebody tried to get into memory. Planting one IS the assertion: admission must refuse every one of them |
| `channel` | `phone` (the default), `web` or `whatsapp`, as the model is told it |
| `expect.writes` | every category named got at least one fact. The words are the org's memory policy, `pinecall memory policy --remember` — a category the policy never names is refused as a bug in the golden, not run |
| `expect.never` | no fact was written under any of these. Your class's own `forget:` words |
| `expect.never_says` | **the sharper one**: no fact CARRIES this value, under whatever category. Matched on the words as they fold and on the digits alone, so `4242 4242 4242 4242` catches `4242424242424242` too |
| `expect.invalidates` | every held fact named here was superseded — and, the mirror, **no other held fact was**. That is the half that catches a model which replaces whatever it touches |

```bash
pinecall remember                                            # every case in agents/<slug>/test/memory/
pinecall remember agents/clinica-norte/test/memory/allergy.json     # one of them
pinecall remember --grep card                                # while writing one
```

```
clinica-norte · anthropic/claude-haiku-5-5 · 3 cases · 3 held · 3672 ms
  ✓ keeps the allergy and never the card
  ✓ mornings replace afternoons, they do not live side by side
  ✓ neither keeps a permission nor erases what nobody denied
```

**Nothing here asks a model whether two sentences mean the same thing.** A fact is natural
language — "allergic to penicillin" and "has a penicillin allergy" are one fact written
twice — so an exact-match assertion would make every golden brittle and useless. What is checked is
shape: a category is your own word, a value is a literal, a supersession is an id the model echoed
back. Every judgment is code, so two runs of one case answer the same thing and a change is a
change and not a mood.

**Where it runs.** Nothing is started here: the gateway runs each case against the agent its holder
declared — your `pinecall start`, a colleague's, production's with `--prod` — because the
categories a golden may name and the tool names admission refuses a fact for are your class's OWN
declaration — Clínica Norte's are `find_patient` and `book`, and a planted sentence naming one of
them is what proves admission reads the declaration and not a list of words. The extraction runs on
the org's model and the org's provider keys: the very call a hang-up makes. **One model call per
case**, which is why this belongs in a nightly and not in every commit.

A case that did not hold prints what broke, then what memory would have kept and what admission
refused — the two together are the whole of why:

```
  ✗ keeps the allergy and never the card
      writes  nothing was written under 'how they like to be addressed'; what was: ['allergies']
      kept      add · allergies · Allergic to penicillin.
```

A golden is fixed and the extraction is the variable. **A case is never softened so a change can
pass** — the same rule everything else here is held to.

## And the read side: does recall bring back the right facts?

`recall` makes the same promise over the other table — the facts this caller taught earlier calls,
the best six of them in front of the model — and it is just as invisible to a ring, for the same
reason. Whether a better fact existed and was missed is something no conversation can answer.

What differs from the index is the question. Nobody can name "the fact that should have won" for a
contact the way they can name a heading in a file they wrote, because a contact's facts are
whatever their earlier calls taught. So a memory question **brings its own facts**:

```json
[
  { "holds": ["Prefers mornings", "Dr. Vidal's patient since 2024", "Allergic to penicillin"],
    "asks": "does Tuesday work for you?",
    "expects": ["Prefers mornings"] }
]
```

| field | means |
|---|---|
| `holds` | every fact memory holds about this question's contact, in the words a fact is written in |
| `asks` | what the caller just said, in their own words — this is the query `recall` is given |
| `expects` | the fact or facts that should come back |

**No contact of yours is read or written.** Each question's facts go to a scratch contact of your
org, `recall` runs, and they are deleted again before the next question — which is also what makes
the figures the real ranking: the same two index scans, the same fusion, the same embedder a call
uses, rather than an arithmetic in a test.

**A fact answers when what came back CONTAINS what you expected**, folded for case, accents and
whitespace. A fact is a sentence a model wrote and you know the substance, not the wording: so
`"Prefers mornings"` is answered by *"Prefers mornings, never after lunch"*, and an expected
`"Allergic to penicillin"` is not answered by *"Allergic"*, which says less than you asked for.

```bash
pinecall memory eval                  # agents/<slug>/test/goldens/memory.json
pinecall memory eval --k 1            # the best fact alone: is the right one first?
```

```
memory · pplx-embed-context-v1-0.6b · 7 questions · recall@6 1.00 · nDCG@10 0.78 · 12107 ms
```

The two figures are the index's two, generalised once: a question may expect several facts, so
`recall@k` is the share of the facts you asked for that came back and `nDCG@10` is normalised by
the best places they could have taken.

**Write questions whose contact holds more facts than a turn asks for.** A turn takes six; a
contact with four gets all four back whatever the ranking did, and `recall@6 1.00` then says
nothing at all. Clínica Norte's golden holds eight or nine per question for that reason, and the
way to make recall bite is a smaller `k`:

```
$ pinecall memory eval --k 1
memory · pplx-embed-context-v1-0.6b · 7 questions · recall@1 0.57 · nDCG@10 0.57 · 11568 ms
  missed: I've been sent for an MRI, can I have it? → wanted Had a pacemaker fitted in 2023, got Prefers to be called Mr. Julián
  missed: they asked me for a back X-ray → wanted Is five months pregnant, got Their usual doctor is Dr. Ferrán
  missed: call me tomorrow at nine to confirm → wanted Works nights, Prefers WhatsApp messages, got Prefers to be called Aixa
```

Every question memory did not answer whole is printed with what came back instead, and the verb
**exits 1** when anything did. A golden is fixed and the ranking is the variable here too: what you
change is the words a fact is written in — the memory policy's `--remember` is that vocabulary — the embedder,
or `k`.

## Is there a score for retrieval on a call?

No, and the reason is worth knowing rather than working around.

`call.score` carries the verdicts of the hang-up judges switched on — LLM judges, every one off
until `pinecall judges on <name>` — and the one that touches retrieval is `grounded`: it
checks that every price, hour, date and name the agent stated appears in the evidence it was given —
and since a lookup arrives as a tool result, that evidence **is** the chunks. So the rate of `held`
over calls carrying a `docs.sources` entry is the precision of retrieval on real traffic, for free.

What no live call can score is whether the index missed a **better** passage, because there is no
truth to compare against outside a golden. The judge says the answer was grounded in what it was
given; the golden says what it was given was the best there was.

What a call does carry, per turn, is the fact of it: `docs.sources` with the query, every chunk and
its score, and `took_ms`; `memory.ops` with the facts recalled; `metrics.eou` with what the lookup
cost the caller in silence. The runtime's `docs/retrieval/spec.md` is the contract for all of it.

