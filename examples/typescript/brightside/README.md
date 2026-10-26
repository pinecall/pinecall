# Brightside: a dot tutor

> The dot tutor is an experiment of Pinecall: its API may change in any release.

Pip is Brightside Dental's front desk as a dot tutor. It is a small face with a pointer of its own,
on the clinic's site, that you talk to: it shows you around, points at what it talks about, and its
prompt reads the page as you scroll. One class, `agents/pip/agent.ts`, extends `Tutor` from
[`@pinecall/dot/agent`](../../../packages/dot/README.md#the-tutor-in-the-agent). Its one walk,
`agents/pip/macros/tour.json`, is the tour of the site in five sentences, each move hung on the word
it belongs to. The page's sections carry lines of their own (`data-pinecall-say`): Pip says one when
you ask what a part is or press the ▶ on it, and all of them as the walk `page`. It fills the
first-visit form with you, field by field, and you press **Book my visit**. The tour is also a walk
you play with no call: `pinecall start` records it in Pip's voice, and the small button beside the dot
plays it (`walks="sandbox"` on the tag).

Two walks are functions, called with what the visitor asks. `times` takes what they want a time for,
types it into the clinic's search, presses **Search times**, waits for the table the search draws
(`/api/times`, a stand-in for the clinic's agenda), and says the row that fits best. `book` takes a
name, a phone and an email and fills the first-visit form with them; the visitor picks the day and
presses its button. In a call Pip passes the params itself. With no call, type in the walks' menu
("Ask me to show you…"): "a cleaning on Thursday", "a time with Dr. Lin", "book it for Jordan Lee,
(312) 555-0142". The page's door (`/pinecall/ask`, the widget's `ask`) picks the params out of what you
wrote with Jev, and records the sentences that name them in Pip's voice.

## Talk to it

```bash
pinecall link                     # once: the org, and its key into .env
pinecall start                    # holds Pip in the sandbox while you edit it
node site/serve.mjs               # the site, on http://localhost:5173
```

Open the page, click the dot in the corner, and say "show me around", or ask where the prices
are. For the menu's field, `OPENROUTER_API_KEY` in `.env` (or the environment) is the door's key to Jev. `site/serve.mjs` serves the page and the one route a site with the widget needs,
`POST /pinecall/token`, which mints the visitor's ticket with the key in `.env`. The key never
reaches the page.

Until a release carries the tutor, the page takes the widget, `@pinecall/room` and `@pinecall/dot`
from this checkout, so build the two packages first (`scripts/build` in `packages/room` and
`packages/dot`). With `DOT_FROM=npm` it takes them from the gateway and jsDelivr instead.

## The pieces

| file | what it is |
|---|---|
| `agents/pip/agent.ts` | the class: its docstring, and `static macros = macros({ tour })` |
| `agents/pip/macros/tour.json` | the walk: what is said, and on which word the pointer moves |
| `agents/pip/macros/times.json`, `book.json` | walks with params: the search with its table, and the form |
| `agents/pip/test/` | the class loads, the walk is checked, the tools are there |
| `site/index.html` | the clinic's page, with `<pinecall-widget look="dot" tutor>` on it |
| `site/serve.mjs` | the page, the token route, the dot's door and the clinic's search, on this machine |
