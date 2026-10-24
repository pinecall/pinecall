# The view, and the blocks of a prompt

The prompt is a list of named **blocks** in two regions, in this order, always:

| region | when it changes | the blocks |
|---|---|---|
| `static` — before the history, cached by the provider | never during a call | `identity` (the class's docstring · the framework's rules and protocols · how to write on the call's channel and medium) · `knowledge` (the page the agent knows by heart, written by the gateway from its settings) · `tools` (every tool's name and docstring) |
| the history — the turns and the lookups, the runtime's; offline, the summaries a `collapse` left | the runtime writes it; the app never does | |
| `dynamic` — after the history, replaced every turn | on every state change | `view` — what `render()` says, the last thing the model reads |

There are four blocks, the same four for every agent. The cut between the two regions is where the
provider's cache is cut, and each block is sent **by name and only when its own text changed**: a
`when` that opens a tool rewrites `tools` and nothing else, and the provider reads `identity` and
`knowledge` back from its cache.

**Every word of every block is yours.** Nothing that arrived from outside the conversation is ever
put in one — not a fact memory kept from an earlier call, not a chunk of a document. Those reach
the model as a **tool result**, in the history, which is the place both vendors name for content a
model should read as information and not as an instruction.

## The view is `render()`

`render()` returns JSX that renders to **text**, never to a page. `this` is the state: the fields,
the getters, `this.call` and `this.remembers(…)`.

```tsx
override render() {
  return (
    <>
      {this.stage === "identify" && <p>Greet the caller and ask for their name and phone.</p>}
      {this.identified && <p>You are talking to {this.patient!.name}, already on file.</p>}
      {this.remembers("usual doctor") && <p>Offer their usual doctor's slots first.</p>}
      {this.call.channel === "phone"
        ? <p>Offer at most two slots.</p>
        : <p>Show up to five slots, one per line.</p>}
    </>
  );
}
```

| you write | the model reads |
|---|---|
| `<p>Ask for their name.</p>` | one paragraph; line breaks and indentation inside it become single spaces |
| two siblings | two paragraphs, one blank line apart |
| `null`, `false`, `undefined` | nothing |
| a string or a number | itself |
| `<>…</>` | its children, with nothing added |

So `{condition && <p>…</p>}` is all the control flow a view needs. A class with no `render()` sends
an empty view. The view is rendered again after every state change, when the caller's turn lands,
when memory recalls something, and when a page claims the call.

## The tags

Imported from `@pinecall/agents`:

| tag | renders as |
|---|---|
| `<Rules>` · `<Protocols>` | their children one per line, inside `<rules>` … `</rules>` or `<protocols>` … `</protocols>` |
| `<Rule>` | one line starting with `- ` |
| `<Section title="…">` | `## title`, a blank line, then its children as paragraphs |
| `<Example>` | its children inside `<example>` … `</example>`, so the model reads an example and not an instruction |

## `@render`: the view beside the class

A view that has grown past one screen can move out of the class. `@render(Prompt)` uses a function
whose props are the instance itself:

```tsx
import { Agent, render, type Stages } from "@pinecall/agents";

const SupportPrompt = ({ stage, customer }: Support) => (
  <>
    {stage === "identify" && <p>Ask for the order number. Nothing else until you have it.</p>}
    {customer && <p>You are talking to {customer.name}.</p>}
  </>
);

@render(SupportPrompt)
export default class Support extends Agent {
  stage: Stages<"identify" | "resolve"> = "identify";
  customer?: Customer | undefined;
}
```

A getter destructures like a field; a method does not, so call it on the agent. A class writes one
spelling or the other, never both.

## What the agent already knows about this caller

`this.remembers("usual doctor")` answers whether memory has told this call something about the
caller under those words. The runtime supplies the facts; a render nobody gave any —
`pinecall prompt`, a test that says nothing about it — answers no rather than guessing.

It is a **question**, and that is the whole of what a view does with memory. The fact itself never
appears in the prompt: it reached the model as the result of the platform's `recall` tool. What
the view adds is the sentence *you* want said when the answer is yes. In a test,
`recalled(agent, ["their usual doctor is Dr. Vidal"])` gives the render something to answer from.

## The channel's words

The `identity` block ends in `<channel>`, how to write for this call: a voice reads everything
aloud, a website's chat can take Markdown, WhatsApp has its own formatting. A class that writes its
own formatting rules turns it off with `channelRules = false`; `this.call.medium` is still there for
a view that branches on voice or text.

## Reading the prompt

`pinecall prompt` prints it with no gateway, no key and no network — the prompt is a function you
can call. One section per block, `── identity (static) ──` … `── history ──` …
`── view (dynamic) ──`, so which half is cached is visible at a glance:

```bash
pinecall prompt                                              # the state a call opens in
pinecall prompt --state agents/<slug>/test/goldens/<a golden>.json  # the state a golden opens in
pinecall prompt --channel web --medium text                  # the prompt a written chat gets
```

In a test it is the same function:

```tsx
import { promptOf, showPrompt } from "@pinecall/agents";

promptOf(agent).blocks.find((block) => block.name === "view")?.text;   // one block, by name
showPrompt(agent);                                                     // the page, under its headers
```

## Collapsing a long call

```tsx
this.collapse("The patient is identified and has heard Tuesday's slots.");
```

The state is untouched. What collapses is the record of how it got here, which is what a long call
runs out of room for. The sentence replaces the instance's change log, the history block
`pinecall prompt` prints under a `<!-- collapsed: … -->`. On a live call the conversation the model
reads is the runtime's, every turn kept: `collapse` writes no entry and does not shorten it.
