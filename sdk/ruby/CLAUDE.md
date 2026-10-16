# pinecall (Ruby) — working agreement

The application's side of Pinecall, in Ruby: a class whose declared fields are the state, whose
`tool` methods are the model's verbs, whose comments are the prompt, and whose ERB view is the
part of that prompt which changes. Reply to the human in Spanish; code, comments and commit
messages in English.

**Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing anything.** §3 is the table that says
what each piece corresponds to in the TypeScript package and why it is different here — a change
that ignores it is a change that makes the two drift. How to build an agent is `docs/`.

## Workflow

```bash
rake              # what CI runs: the tests, the example's own suite, then the signatures
rake test
rake examples     # the ring-0 suite a customer writes, run the way they run it
rake ring1        # the example's goldens through the one CLI and the gateway; needs the CLI and a key
rake rbs

ruby -Ilib -r pinecall -e 'exit Pinecall::Serve.main(ARGV)' -- prompt --file agent.rb --slug x   # what the CLI runs
```

This gem is a library and ships no executable: the verbs are the one `pinecall` CLI's (npm), which
starts `Pinecall::Serve.main` for `prompt`, `chat`, `test` and `start`. A verb, a console screen or
a REST door the CLI reaches is never added here.

## Structure

`lib/pinecall/agent*` is the class, `lib/pinecall/client*` is the socket, `bridge.rb` is the only
place the two know about each other, and `view.rb` + `blocks.rb` are the prompt. Nothing in
`lib/pinecall/agent/` may know what a websocket is.

## Docs are part of the change

A change lands with the page that describes it, in the same commit.

| you changed | you edit |
|---|---|
| a module, an entity, the correspondence with the TypeScript package | `ARCHITECTURE.md` |
| the serve entry, `Pinecall.serve`, how a server runs the agent | `docs/` and ARCHITECTURE §10 |
| anything a person writing an agent types | the `docs/` page for it |
| a rule that is refused at load | `docs/`, with the sentence the refusal says |
| anything a user would notice | `CHANGELOG.md`, under Unreleased |

Before renaming anything public: `grep -rn "<old name>" lib test examples docs *.md sig`.

When a doc and the code disagree, the code is what happened and the doc is the bug.

## Rules the tests enforce

- **Tools are the only writers of state.** A write with no author raises `UnauthoredWrite`. The
  author rides `Fiber[]`, never a module-level variable: one process serves many calls at once.
- **A declaration is refused at load, never at the first call.** No docstring, a positional
  argument, a stage the class never declared, `pii:` naming a parameter that is not there.
- **Only the block whose text changed is sent again**, by name. A static block goes up once per call.
- **The prompt is four named blocks in two regions, in this order:** `identity` · `knowledge` ·
  `tools` (static, cached) · the append-only history · `view` (dynamic, replaced every turn).
  Never reorder, and the dynamic region is the view and nothing else.
- **Every block is the tenant's own words.** What memory kept and what the knowledge base returned
  never enter the prompt: the platform runs `recall` and `search` and their answers reach the model
  as tool results, in the history. A view may ask `remembers?("…")`; it may never print a fact.
- **A static block cannot read the state.** It is rendered against a reading that refuses by name.
- **Nothing here imports LiveKit, a model vendor, or the runtime.** Commands out, entries in.
- **The wire is the runtime's, kept in `lib/pinecall/wire/`**: the shapes this gem uses and no
  more, held to the runtime's golden log by `test/wire/reduce_test.rb`. A field this package needs
  lands in the runtime's wire first, then here by hand.

## What a review comes back to

- One definition per thing. Before writing a constant or a helper, `grep -rn` for it.
- No dead code and nothing "for later". A symbol with no user outside its own file and its own
  test is deleted by the card that notices it.
- No module-level mutable state. Per call, per mount, or on the fiber.
- Every file opens with a line saying what it is. 400 lines is the ceiling, 150 the norm.
- Tests read as sentences: `test_a_write_outside_a_tool_is_refused_by_name`.

## Traps — each one cost an afternoon

- **`method_added` fires for every method**, including the ones this package defines itself. The
  guard is `@pending_tool` being nil; do not add a second mechanism beside it.
- **A thread that waits for an entry must not be the thread that reads them.** `agent.register` is
  answered by an entry, so the declaration goes up on its own thread. That was a real deadlock and
  `test/client/socket_test.rb` is what found it.
- **A view asks, it never prints.** `remembers?("médico habitual")` is the one thing a template
  does with memory, and the runtime answers it. A fact reaches the model as a `recall` tool
  result; splicing one into a block gives an earlier caller's words operator authority.
- **A state default that is a literal `[]`** is duplicated per instance on purpose. If you change
  `opening`, check that two calls never share one list.
- **zsh `noclobber`**: `cat > file` refuses to overwrite and leaves the old file in place. `>|`.

## Commits

Versions and tags are the human's call — never pick a number, never tag. A `v*` tag of the
repository is the release: the root's `release.yml` checks the tag against every package's version
(`lib/pinecall/version.rb` here, written by the root's `scripts/version`), runs `check.yml` (`rake`
on Ruby 3.2, 3.3 and 3.4 among them) and pushes the gem by Trusted Publishing, environment
`rubygems`. `gh workflow run release.yml` rehearses it without publishing.

## Comments and doc comments

The bar is an open-source library: plain technical English, and less prose than code.
- A comment says WHY, only when the code cannot: a constraint, a trap, an external fact. Never
  what the next line does. One line by default, three at most; more belongs in `docs/`.
- No history in code (dates, incidents, "until X this did Y"): that is the commit message.
- Public API keeps a concise doc comment a user reads in their editor; internals need none unless
  the name is not enough. No figures of speech.
