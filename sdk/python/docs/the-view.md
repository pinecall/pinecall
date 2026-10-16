# The view, and the blocks of a prompt

The prompt is a list of named **blocks** in two regions, in this order, always:

| region | when it changes | the blocks |
|---|---|---|
| `static` — before the history, cached by the provider | never during a call | `identity` (the class's docstring · the framework's rules and protocols · how to write on the call's channel and medium) · `knowledge` (the page the agent knows by heart, written by the gateway from its settings) · `tools` (every tool's name and docstring) |
| the history — the turns, the lookups, and the summaries a `collapse` left | the runtime writes it; the app never does | |
| `dynamic` — after the history, replaced every turn | on every state change | `view` — the last thing the model reads |

There are four blocks, the same four for every agent. The cut between the two regions is where the
provider's cache is cut, and each block is sent **by name and only when its own text changed**: a
`when=` that opens a tool rewrites `tools` and nothing else, and the provider reads `identity` and
`knowledge` back from its cache.

**Every word of every block is yours.** Nothing that arrived from outside the conversation is ever
put in one — not a fact memory kept from an earlier call, not a chunk of a document. Those reach
the model as a **tool result**, in the history, which is the place both vendors name for content
a model should read as information and not as an instruction.

## The view is a template, beside the class

A Jinja template: a file of its own, mostly prose with holes in it, rendered with the state in
scope. The object renders itself. `views/<slug>.jinja`, beside the file the class is written in —
the convention this package has instead of a setting.

```
agents/clinica-norte/
  agent.py
  views/clinica-norte.jinja
```

```jinja
{% if stage == "identify" %}
Greet the caller and ask for their name and phone. Nothing else until the patient is identified.
{% endif %}

{% if identified %}
You are talking to {{ patient.name }}, already on file: do not ask for their name again.
{% endif %}

{% if remembers("usual doctor") %}
Offer their usual doctor's slots first.
{% endif %}

{% if call.channel == "phone" %}
Offer at most two slots.
{% else %}
Show up to five slots, one per line.
{% endif %}
```

In scope:

| name | what it is |
|---|---|
| every state field, by its own name | derived fields (a public `@property`) included |
| `call.channel`, `call.medium`, `call.claimed` | the call: `phone`, `web` or `whatsapp`; `voice` or `text`; the page's code it claimed, or none |
| `resumed` | the call picks up one that was cut |
| `remembers("…")` | whether memory holds something about this caller matching those words |

A tag on a line of its own leaves no line behind, which is how a template stays readable and its
output stays tight. Whatever slips through is tidied anyway: no trailing spaces, never more than
one blank line in a row, nothing hanging off either end. A name the template uses and the class
never declared raises, by name, rather than rendering as nothing. `{% include "part.jinja" %}`
reads from the same `views/` folder.

Small enough to live inside the class, it can:

```python
class Recepcion(Agent):
    view_template = """
{% if stage == "identify" %}
Greet the caller and ask for their name and phone.
{% endif %}
"""
```

A subclass with no view of its own renders its parent's.

## What the agent already knows about this caller

`remembers("usual doctor")` answers whether memory holds something about this caller matching
those words. The runtime supplies the facts; a render nobody gave any — `pinecall prompt`, a test
that says nothing about it — answers no rather than guessing.

It is a **question**, and that is the whole of what a view does with memory. The fact itself never
appears in the prompt: it reached the model as the result of the platform's `recall` tool, in the
history. What the view adds is the sentence *you* want said when the answer is yes.

```python
render(agent, remembered=["their usual doctor is Dr. Vidal"])["view"]
```

## Reading the prompt

`pinecall prompt` prints it with no gateway, no key and no network — the prompt is a function you
can call. One section per block, `── identity (static) ──` … `── history ──` …
`── view (dynamic) ──`, so which half is cached is visible at a glance. In a test it is the same
function:

```python
from pinecall import Line, render, show_prompt

prompt = render(agent, Line(channel="web", medium="text"), resumed=True)
prompt["view"]  # the text of one block, by name
prompt.static()  # the blocks before the history, in send order
prompt.instructions()  # those joined: the one text the provider caches
prompt.blocks  # every block, in send order
show_prompt(agent)  # the page, under its headers
```

With no `Line`, the prompt is a phone call's.

## Collapsing a long call

```python
self.collapse("The patient is identified and has heard Tuesday's slots.")
```

The state is untouched. What collapses is the record of how it got here, which is what a long call
runs out of room for. The sentence lands in the history under a `<!-- collapsed: … -->`.
