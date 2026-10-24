# Brightside: a dot tutor

Pip is Brightside Dental's front desk as a dot tutor. It is a small face with a pointer of its own,
on the clinic's site, that you talk to: it shows you around, points at what it talks about, and its
prompt reads the page as you scroll. One class, `agents/pip/agent.ts`, extends `Tutor` from
[`@pinecall/dot/agent`](../../../packages/dot/README.md#the-tutor-in-the-agent). Its one walk,
`agents/pip/macros/tour.json`, is the tour of the site in five sentences, each move hung on the word
it belongs to.

## Talk to it

```bash
pinecall link                     # once: the org, and its key into .env
pinecall start                    # holds Pip in the sandbox while you edit it
node site/serve.mjs               # the site, on http://localhost:5173
```

Open the page, click the dot in the corner, and say "show me around", or ask where the prices
are. `site/serve.mjs` serves the page and the one route a site with the widget needs,
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
| `agents/pip/test/` | the class loads, the walk is checked, the tools are there |
| `site/index.html` | the clinic's page, with `<pinecall-widget look="dot" tutor>` on it |
| `site/serve.mjs` | the page and the token route, on this machine |
