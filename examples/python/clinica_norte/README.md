# Clínica Norte

A whole agent, written the way a customer writes one, on the one CLI's layout: the same agent as
the TypeScript example (`examples/typescript/clinica-norte`) and the Ruby one
(`examples/ruby/clinica_norte`), with the same agenda, the same documents and the same eleven
goldens, in Python. Its prompt is, byte for byte, the Ruby example's for every golden's state.

The clinic is Spanish and so is everything its callers hear: the class's docstrings, the view and
the goldens are in Spanish on purpose. The framework's own rules are English, and tell the model to
answer in the caller's language.

```
agents/clinica-norte/agent.py                    the class: state, stages, tools
agents/clinica-norte/agenda.py                   the clinic's agenda, made up and fixed: what its API would be in production
agents/clinica-norte/views/clinica-norte.jinja   the view: the `view` block, as a function of the state
agents/clinica-norte/docs/*.md                   what it answers from, per turn: `pinecall docs push` uploads them
agents/clinica-norte/test/test_clinica.py        ring 0: no network, no key, no model, no gateway
agents/clinica-norte/test/goldens/               ring 1: eleven conversations, plus docs.json and memory.json
agents/clinica-norte/test/memory/                the extraction cases `pinecall remember` runs
```

The folder is named after the agent's slug: `agents/clinica-norte/` is the agent `clinica-norte`.
A folder with a dash cannot be imported, so the test loads the class with `pinecall.testing.load`,
the way `pinecall start` loads it: its folder a package, so `agent.py` imports
`from .agenda import …`.

```bash
# the customer's own suite, run the way they run it, with this checkout's SDK
(cd ../../../sdk/python && make examples)

# the rest, with the one CLI (npm i -g pinecall), from this folder
pinecall prompt --state agents/clinica-norte/test/goldens/no-reserva-antes-del-si.json
pinecall chat
pinecall test                    # ring 1: make ring1 from sdk/python
pinecall start
```

The CLI never loads the class: it starts `python -m pinecall.serve` with the project's own
interpreter, `.venv/bin/python` ([production.md](../../../sdk/python/docs/production.md)). In this
checkout that `.venv` is the SDK's (`sdk/python`): `make ring1` links it before running the goldens.

What the front desk knows by heart — hours, prices, what needs an authorisation — is not in this
repository: it is written in the console, Settings ▸ Knowledge (or `pinecall agent knowledge
edit`), and the model reads it whole on every call. The voice, the model, the greeting, the
language, what memory keeps (`pinecall memory policy`) and the base it searches per turn
(`pinecall docs attach clinica-norte --k 4`) are the world's, not the class's, and a class that
still declares one is refused on import.

## What this example teaches

- **A stage moves the tools.** `stage: Literal["identify", "choose", "book", "done"]` is a state
  field like any other, and `stage=` on a tool is sugar over `when=`.
- **A slot is booked by its id, never by its time.** Two slots at the same hour with different
  professionals are indistinguishable in words; one id looks like no other, and one the agenda
  never offered is refused with the list of those it did.
- **`propose` and `book` are two moments.** Without the `proposed` field the view cannot tell
  whether to read the time back or to book it, and an obedient model reads it back again instead
  of booking.
- **The day is resolved to a date in code.** "Tuesday" said on a Thursday is one date and one
  only; a day with no agenda comes back empty, and the view names it.
- **`confirm=` is what makes `book` irreversible on the wire.** The platform reads the sentence
  after the booking, with what the tool returned.
- **`preview=2` cuts what the model sees, not what the state keeps.**
- **The agenda is a collaborator, not state.** A `cached_property`: each call has its own, and it
  appears in no snapshot.
- **The view is only what the clinic writes.** What memory recalled and what the base answered
  reach the model as a tool result, in the history. The view asks `remembers("médico habitual")`
  and decides on a sentence of its own with the answer.
