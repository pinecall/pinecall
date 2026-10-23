# Retrieval — what a call looks up, when, and how it is measured

An agent that answers from documents makes two promises: that what it says is in the documents,
and that saying it does not make the caller wait. Both are numbers, and both are in the call's own
log. This page says what a lookup is, when it runs, what the log keeps of it, and which figures a
tenant can compute from entries they already have. A retrieved passage reaches the model as data
inside a tool result, never as an instruction, and it never carries the operator's authority.

## The two lookups

| tool | answers | from | runs when |
|---|---|---|---|
| `search` | up to `k` chunks of the bases the agent reads | the knowledge bases pushed to the org | early, once a spoken caller has said four words; else when the turn ends; only on a turn that could be a question |
| `recall` | up to six facts held about this contact | the contact's memory, taught by earlier calls | the same moment, when the agent keeps memory and the platform knows who is on the line |

Both are tools of the platform, never of the app. With a base attached as `retrieved` (the
default of `pinecall docs attach`) the platform runs `search` before each turn and splices the
answer into the request as a tool result; with `mode: tool` the platform runs nothing before the
turn. In both modes the model holds `search` whenever a base is attached, and calls it when it wants
to. `recall` runs before each turn whenever the agent declares a memory policy, and the model holds it
as a tool the same way. Either way the model
reads the same shape: `{"chunks": [{path, heading, text}]}` and
`{"facts": [{text, source, since}]}`, with no score in either, because a score means something
to the ranking and nothing to the model.

A lookup starts on the first transcript worth a query (four words or more, with a letter in them),
interim or final, so its answer is usually
in before the turn ends: ears that write interims start it while the caller still talks, and ears
that write none (Whisper) start it on the final, while the end of the turn is still being weighed.
What a turn waits for it is a budget: 250 ms on a spoken call, 3 s on a written one
(`PINECALL_VOICE_LOOKUP_BUDGET_MS`, `PINECALL_TEXT_LOOKUP_BUDGET_MS`). A turn no transcript started
a lookup for (shorter than four words, or written) is looked up when it ends, within the same budget.
A lookup that is late is cancelled and the turn goes on without it; a late lookup, and one that cannot
run at all, is a recoverable `error` entry, `search_skipped` or `recall_skipped`, saying why. A lookup started early is a
guess at the question from its first words; the turn's text is the question. When the text says
more than the early run was given, it is looked up again and waited for within the budget, and
the early answer stands in for a late one, so a spoken turn is never answered from "hi, I wanted
to ask" when "what do Saturdays cost" came in time. Each pair in the request records the query it
answers. Every turn is searched on its own words alone: a follow-up ("and how much is that?") is
searched without the turn before it, which is what a tool that searches is for, its query written
by the model with the whole conversation in front of it.

Neither runs on a turn with no letter in it: a number being read out finds nothing in a prose
index, and a caller's digits are the last thing to send to an embedder.

## Why a score cannot decide whether to look

A chunk's score is its fused rank read relative to the best of that query, so the top chunk is
1.0 whatever was asked. Reciprocal-rank fusion produces sums that are not comparable between two
queries, which is why they are normalised. `min_score` therefore cuts the tail of an answer and
can never say "nothing here answers this": a relative score orders, it does not judge. The
judgment is made before the search, on the words, and it is deliberately the whole of it.

## What a base is made of

A base is a folder of Markdown pushed whole (`PUT /v1/knowledge/{base}`) or a file at a time
(`PUT /v1/knowledge/{base}/files/{path}`). Each file is cut at its headings, one to three hashes,
each piece kept under 350 tokens and cut again at a paragraph or a sentence when a section runs
long; a fenced code block is one paragraph whatever blank lines it holds, and is never cut, so a
class is never split between two of its members. A piece carries its heading path in the text
both indexes read, `Tarifas › Revisión`. Front matter is not a chunk, and an HTML comment never
reaches one: it is the author's, dropped from the body outside a code fence. **One comment is
read**: an `asks` comment, the questions the section answers, one a line:

```markdown
## Co-payments

<!-- asks
how much is my co-payment?
do I pay anything at the visit?
-->

A visit is fifteen euros at the desk, the rest is billed to the insurer.
```

Each question is a row of its own beside the section's first piece, embedded alone as a query is,
so it sits in the space the callers' questions arrive in; found, it hands back the section's text,
never itself, and a question and its section found together are one hit. A question counts as a
chunk against the quota. Invisible on any site that renders the file, the questions are written by
the author beside the text they answer, or generated from it by a script and kept with the
documents, never maintained apart from them. A file keeps the SHA-256 of the text it was cut from, so a push embeds only
the files that changed and the rest are kept as they were; a push that changes nothing costs one
transaction and no embedding.

Every chunk is found by its vector and by its words: one query embedded once, one scan of the
HNSW index and one top-`room` scan of each BM25 index asked, each a ranked list of its own, fused
by reciprocal rank in SQL (a row's score is the sum of 1 / (60 + rank) over the lists it is in).
Two BM25 indexes score over two corpora, so their scores are never ordered together: only ranks
are. The statement is planned for its values on every search (`plan_cache_mode`): a plan made once
for any org and any copy estimates a copy at a few dozen rows and scores every row by hand, a
second where the two index scans take ten milliseconds. **A base speaks a language**: the text-search
configuration its words are stemmed with, one of `english`, `spanish`, `portuguese`, `french`,
`german`, `italian`, `dutch` or `simple` (no stemming), said by the push (`language`, as `en` or
`english`) or counted from the files' function words when it says none, `simple` when they say
nothing clearly (a table of names); the push's answer says which. A base begun with a file that
said nothing clearly is counted again with every file put beside it, so the prose that follows a
table makes the base speak. Each language has a partial BM25 index of its own over the
chunks in it, so `supervise` finds *supervising* in an English base and *sábados* finds *sábado* in
a Spanish one; a file put beside the others speaks the base's language, and a folder pushed again
in another language moves every chunk kept to the new index without embedding it again. Several
bases in several languages searched together read each language's index over its own rows, one
ranked list each. A contact's memory is still read with the Spanish
configuration (deferred, below).

What a turn is handed is sections, not loose pieces, as megabrain handed them in v1: a chunk found
comes back as its section, the chunks of the same heading two either side of it joined in the
file's order, so a section cut at 350 tokens reads whole again. Two hits in one section come back
once. The two best pages give every section found in them; every page after them gives only its
best one, so the answer reads the right page whole and the rest of the base one line each. An org's chunks
count against its `knowledge_chunks` quota, sized before the push, and a plan with the quota at
zero searches nothing and writes no entry.

What belongs in a base is what the agent should look up: tariffs, hours, procedures, the long
tail. What belongs in the agent's own `knowledge` block, the Markdown the class ships, is what it
should always know: who it is, what it may promise, the handful of facts every call needs. The
block is read on every turn and cached by the model's provider; a base is read when the turn
asks for it.

## Several bases, one search

An agent reads every base attached to it, and a turn searches all of them in one pass: one
embedding, both branches over the union, one fusion over everything that came back, then each
chunk against the floor of its own attachment. Searched one at a time and merged afterwards, each
base would answer 1.0 for its own best chunk whatever it was about, and a collection with nothing
to say about the question would take a slot all the same.

`k` is the turn's, the most generous of the attachments (eight by default), and an app that asks
`this.knowledge.search(query, {k})` may say its own; `min_score` is the attachment's. The
candidate pool grows with the bases asked, thirty per branch per base, so a small collection is
not crowded out before it is read. `docs.sources` says which base each source came from.

## Memory

A contact is the app's contact id when it named one, else the number the call came from; a web
visitor nobody named has no memory. At hang-up, between `call.ended` and `call.summary`, the
platform reads the call's turns, asks the agent's own model, on the keys the org's calls run on (its own, or the box's where its
plan lends them), what the call
taught about the contact, and writes what it answers embedded. The policy's `remember` words are
the categories the model is asked to keep; the code refuses only a fact filed under one of the
`forget` words (matched as a word, case aside) and a fact that names one of the agent's tools. A
fact under another category, or none, is written. A policy that remembers nothing asks no model.
That model call is the whole cost of a hang-up and it has a budget, `PINECALL_REMEMBER_BUDGET_S`
(8 s): past it, or broken, the log carries a recoverable `remember_failed` and the call seals all
the same. An org at its `memory_facts` cap asks no model: the refusal goes on the agent's log as
`credits.exhausted` and the call's says an empty `remember`. A memory at its cap is still read,
since a cap is about keeping.

`recall` ranks the contact's current facts by the same two branches, then by recency and the
confidence the extraction gave them, and hands the model the best six with the call that taught
each and the date it was first held. The contact recalled is the one the platform knows, never one
the model wrote into its arguments.

## What the log carries

| entry | fields |
|---|---|
| `docs.sources` | `query`, `sources[{id, base, path, heading, score, excerpt}]`, `took_ms`, `speech_id` |
| `memory.ops` | `ops[{op, contact, query, facts[{id, text, category, score, source}], took_ms}]`, `speech_id` |
| `error` | `code` in `search_skipped`, `recall_skipped`, `remember_failed`; `recoverable: true` |
| `metrics.eou` | `on_user_turn_completed_delay`: what retrieval cost the person on the line |
| `metrics.llm` | `prompt_tokens`, `prompt_cached_tokens`: what the passages cost in tokens |

A lookup the model called carries the `speech_id` of the line it was called on. A lookup the
platform ran before the turn carries none: it runs before the turn's item exists, so it is joined
to its turn by order, the `docs.sources` and `memory.ops` entries written before a `turn.user`
being that turn's. A turn looked up twice, early on its first words and again on its whole text,
carries an entry for each run that finished, and the request holds only one of their answers: the
final one, or the early one standing in for it. No entry is written when a lookup did not run: an empty `docs.sources` would read to the grounded
judge as a search that found nothing.

## The figures

1. **The silence retrieval costs** is livekit's own `on_user_turn_completed_delay`: the callback
   it times is where the session collects its lookups. Target: p95 under 50 ms, because a lookup
   started on a transcript is usually back before anybody waits.
2. **Turns that went without** is `count(error where code in (search_skipped, recall_skipped)) /
   count(turn.user)`. Target: under 1 %. Above it the fix is the budget, the embedder or the
   database, never a larger budget: a budget always met is a budget the caller pays in silence.
3. **What the passages cost** is `prompt_tokens` on a turn that retrieved against one that did
   not; `k` and `min_score` are the knobs.
4. **Whether the cached prefix holds** is `prompt_cached_tokens / prompt_tokens` from the second
   turn on. Target above 0.8, with the caveat that a provider caches nothing under its minimum
   prefix.

## Quality

The figures say retrieval was fast and cheap, not that it found the right passage. That is judged
twice. On every call, the hang-up panel's `grounded` judge checks what the agent stated against
the chunks it was handed, so the rate of `held` over calls carrying `docs.sources` is the
precision of retrieval on real traffic, at no extra cost. Offline, a golden per base
(`POST /v1/knowledge/{base}/eval`: `{questions: [{asks, expects}], k}`, `expects` a heading path a person can
write by reading their own documents, or a list of them any one of which answers) gives
`recall@k` and `nDCG@10` by code alone (how to raise them, step by step, is
[A knowledge base that answers](a-knowledge-base-that-answers.md)); a golden per
agent's memory (`POST /v1/contacts/memory/eval`: `{questions: [{holds, asks, expects}], k}`) writes each
question's facts to a scratch contact, asks, and deletes them, so what is measured is the ranking
a call would get. A question is never softened so a change can pass. A memory fact answers when
what came back contains what was expected, accents dropped, case folded, spaces squeezed: a golden
knows the substance and not the wording.

## Deferred, and named

- **A reranker.** An absolute signal over the candidates would let a score gate a lookup; it is a
  different design, and it waits for a golden that says what the fusion misses.
- **A reranker's place is known.** After the fusion and before the sections, on every lookup the
  model calls and on every written turn; on a spoken turn only when it is back within the
  budget, the fused order handed over otherwise and the entry saying so. A self-hosted
  cross-encoder (bge-reranker-v2-m3 on one GPU) scores sixty candidates in 50–110 ms; a hosted one
  takes 170–460 ms, which no spoken turn has beside the embed.
- **BM25 first as a gate.** A short turn with a low lexical score need not be embedded at all;
  measurable with figure 3 once the golden exists to say what it costs in recall.
- **A monitor over `memory.ops`**, reading for a fact that reads like an instruction.
- **Memory in the call's language.** `contact_memories` has the one Spanish index; a fact is
  written in the call's language, which the agent declares, so the same partial index per language
  fits once a golden of English callers says what the Spanish stemmer misses.
