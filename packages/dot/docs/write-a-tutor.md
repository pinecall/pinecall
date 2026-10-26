# Write a tutor agent

> **Experimental.** `@pinecall/dot` may change in any release. This page is true of the version it ships with.

A tutor is an agent that is also a person on your site: a dot in the corner that talks, and a
pointer of its own that shows the visitor where things are. It never clicks or sends anything for
them. This page takes you from an empty agent to one that answers a call, gives guided walks, and
draws your own tools' results on the screen. Each step runs on its own, so stop where you have what
you need.

You need a Pinecall agent project (`pinecall new`, the [tutorial](https://docs.pinecall.io/start/tutorial/))
and a site you may edit.

## 1. The agent extends `Tutor`

```bash
pnpm add @pinecall/dot @pinecall/agents
```

```tsx
// agents/pip/agent.tsx
import { macros, Tutor } from "@pinecall/dot/agent";

/**
 * You are Pip, Brightside Dental's front desk, on the visitor's screen. Short sentences: everything you
 * say is read aloud. Show them where things are on the page; never say you clicked something for them.
 */
export default class Pip extends Tutor {
  static override macros = macros({});
}
```

That is a tutor. `Tutor` adds the pointer's tools (`point`, `highlight`, `scrollTo`, `fill`, `home`
and the rest), the page's events, and a view that prints the screen the visitor sees. If your class
has a `render()` of its own, end it with `{this.seeing()}`, or the model never reads the page:

```tsx
override render() {
  return (
    <>
      <p>Ask for the visitor's name before anything else.</p>
      {this.seeing()}
    </>
  );
}
```

A call that no tutor's page joined (the phone, a chat, a site with no dot) is the agent's alone:
the pointer's tools stay hidden and the view says nothing of a screen. One class serves both.

Hold it in the sandbox with `pinecall start`, as any agent.

## 2. The site draws the dot

The quickest way is the widget:

```html
<script type="module" src="https://cloud.pinecall.io/widget/pinecall-widget.js"></script>
<pinecall-widget agent="pip" look="dot" tutor token-url="/pinecall/token"></pinecall-widget>
```

`token-url` is a door of yours that mints a seat for the visitor with your org's key (never put the
key on the page; [tokens](https://docs.pinecall.io/api/tokens/)). Add `walks="sandbox"` while you
build, to read the sandbox's walks.

To own the code, build it from the two packages the widget uses:

```ts
import { room } from "@pinecall/room";
import { tutor } from "@pinecall/dot";

let pip: ReturnType<typeof tutor> | null = null;
const call = room({
  tokens: (scope, resume) => ticket(scope, resume),   // your door's answer
  gateway: "https://cloud.pinecall.io",
  onUi: (data) => void pip?.take(data),
});
pip = tutor(call, {
  label: "Talk to Pip",
  onClick: () => { pip?.wake(); void call.start("talk"); },   // inside the click: audio starts only there
});
```

Open the page, click the dot and ask "what's on this page?". The agent reads the page as roles and
names, the way Playwright's aria snapshot does, so **name the parts you want it to find**: a
`<section>` needs an `aria-label` or `aria-labelledby` to be a region; a `<div>` you want to point
at needs `role="group"` and an `aria-label`. [The README](../README.md#the-page-as-the-agent-reads-it)
shows what the agent sees.

## 3. Write a macro

A macro is a guided walk: sentences the agent says as written, with moves hung on their words. Save
it as `agents/pip/macros/tour.json`:

```json
{
  "name": "tour",
  "title": "Site tour",
  "when": "the visitor asks to be shown around",
  "steps": [
    {
      "say": "Up here are our services. Whitening is the one most people ask about.",
      "beats": [
        { "word": "Up", "do": "scroll_to", "find": ["region", "Services"] },
        { "word": "Whitening", "do": "highlight", "find": ["article", "Whitening"] }
      ]
    }
  ]
}
```

and give it to the class:

```tsx
import tour from "./macros/tour.json" with { type: "json" };

static override macros = macros({ tour });
```

Now "show me around" in a call runs it, and `pinecall start` records it as a walk (step 4). The
[macro reference](macros.md) has every field, the moves, and how to write one that holds up.

## 4. Walks a visitor plays with no call

As the agent starts, `Tutor` records each sentence of each macro once, in the agent's own voice,
and publishes them. The terminal says so:

```
pip  walk tour · 5 sentences · 0:38 · cartesia sonic-3 …
```

A visitor then plays them from the dot's menu with no call and nothing spent. Turn it on by naming
where the walks are published:

```html
<pinecall-widget … walks></pinecall-widget>          <!-- production's; walks="sandbox" for the sandbox's -->
```
```ts
tutor(call, { walks: "https://cloud.pinecall.io/v1/agents/pip/public/walks" });   // ?env=sandbox for the sandbox's
```

`pinecall walks list` shows what an agent published and `pinecall walks play tour` plays it in your
terminal. A sentence you did not edit costs nothing the next time; one you edit is recorded again.

**Show some walks on some pages.** Name the pages in the macro (`"pages": ["/security"]`) and the
menu, and the agent in a call, offer it only there; with no `pages` a walk is for every page
([Macros](macros.md#walks-for-some-pages)).

**Tie a walk to the page.** A section marked `data-pinecall-walk="tour"` makes the menu mark that
walk while the visitor is on that section. A button of yours marked `data-pinecall-play="tour"` and
`hidden` is shown while that walk can play, and a click plays it:

```html
<section id="services" data-pinecall-walk="tour" aria-labelledby="services-h">…</section>
<button data-pinecall-play="tour" hidden>Show me around</button>
```

## 5. Say one thing without a macro

Mark any element with the line it should say:

```html
<article data-pinecall-say="Family Care covers up to four people for thirty-nine dollars a month.">
```

The agent says it, with the pointer on the element, when the visitor asks about it or presses the ▶
that shows on it during a call. See [Lines on the page](../README.md#lines-on-the-page).

## 6. Draw your own tools' results

An agent has tools of its own: free times, a booking, a piece of code. Their results are on the
call's log, so the page says how to draw each by the tool's name, on a card above the dot:

```ts
tutor(call, {
  views: {
    freeSlots: (host, result, tools) => {
      const { times } = result as { times: string[] };
      host.innerHTML = times.map((time) => `<button>${time}</button>`).join("");
      host.onclick = (event) => tools.send((event.target as HTMLElement).textContent ?? "");
    },
  },
});
```

With the widget, set `widget.views = { … }` on the element. A view may draw anything (React included:
`createRoot(host)`, and return `() => root.unmount()` to take it down). `tools.send(text)` says
something to the agent in writing, as the visitor; `tools.hide()` puts the card away.

**Two things to get right:**

- **The log must carry the tools.** A visitor's seat reads the call's log through the *public*
  projection, which holds no tool runs. Your token door has to ask for the tenant's: `log: "tenant"`
  when it mints (`mint(key, { …, log: "tenant" })` in `@pinecall/room/server`). Without it no card
  ever appears and nothing says why.
- **The log masks what the agent declared private.** A tool argument listed under `pii` reads
  as `***` there. To fill a form with what the visitor said, have the tool tell the page, to this
  visitor alone:

  ```ts
  if (this.onScreen()) this.call.send("pinecall.ui", { type: "form.fill", name, email });
  ```

  and handle it in `onUi` (`tutor.take(data)` is `false` for a message that is not its own):

  ```ts
  onUi: (data) => { if (pip?.take(data)) return; if (isFormFill(data)) fillMyForm(data); }
  ```

## 7. Let the visitor type what to show

```ts
tutor(call, {
  ask: (request) => fetch("/api/ask", { method: "POST", body: JSON.stringify(request) }).then((r) => r.json()),
  onTalk: (message) => startACallAndSay(message),
});
```

and on your server, with an OpenRouter key, and your Pinecall key for the sentences with slots:

```ts
import { answer } from "@pinecall/dot/server";
const voicing = { key: process.env.PINECALL_KEY, agent: "pip" };
export const POST = async (request) => Response.json(await answer(await request.json(), { key: process.env.OPENROUTER_API_KEY, voicing }));
```

The walks' menu gets a field, "Ask me to show you…". The dot plays a walk, with the params picked out
of what was typed, or points at a thing; a question it cannot show goes to the agent through `onTalk`.
A walk that takes params is a function the visitor calls by asking: "book it for Jordan Lee,
jordan@lee.dev" fills the form, "a cleaning on Thursday" searches your times and reads the row that
fits ([macros](macros.md#a-macro-as-a-function)). Pace the door per visitor: it spends your keys.

## 8. Try it, then ship it

1. `pinecall start` holds the agent in the sandbox and records its walks there.
2. Serve your site, with the dot's walks pointing at the sandbox (`walks="sandbox"`), and talk to it.
   Everything a laptop does stays in the sandbox.
3. `pinecall deploy` runs it in production, where it records its walks as it starts; the dot's
   `walks` then points at production's.

## What the tutor will not do

It never submits a form or opens another page for the visitor: the one button it presses is one your
macro names, outside any form or in a search form. It writes into a field only
what the visitor told it, never into a password, a card, a file or a hidden field. The page's words
reach the model fenced as data, never as instructions: put what other people wrote (reviews,
comments) under `data-pinecall-skip` so the agent does not read it at all.
