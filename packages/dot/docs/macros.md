# Macros

> **Experimental.** `@pinecall/dot` may change in any release. This page is true of the version it ships with.

A macro is a guided walk, a JSON file in the agent's folder (`macros/<name>.json`). The agent says
each step as written; the page runs each step's moves as their words are said. The same file is
what a visitor plays with no call (a *walk*, recorded in the agent's voice). [Write a tutor
agent](write-a-tutor.md) shows where it goes; this page is the format.

```json
{
  "name": "plans",
  "title": "Plans and prices",
  "when": "the visitor asks what it costs, or which plan to choose",
  "steps": [
    {
      "say": "Here are our three plans: one monthly price instead of a surprise bill.",
      "beats": [
        { "word": "Here", "do": "scroll_to", "find": ["region", "Pricing"] },
        { "word": "three", "do": "highlight", "find": ["region", "Pricing"] }
      ]
    },
    {
      "say": "Family Care is the one most families pick.",
      "beats": [
        { "word": "Family", "do": "highlight", "find": ["article", "Family Care plan"] },
        { "word": "pick", "do": "point", "find": ["article", "Family Care plan"] }
      ]
    }
  ]
}
```

## The file

| field | |
|---|---|
| `name` | what the model names it in `runMacro`. The key it is given in `macros({ plans })` when left out |
| `title` | the visitor's button: "Plans and prices". `name` when left out |
| `when` | when to run it, in the words the model reads: "the visitor asks what it costs" |
| `pages` | the paths of the pages it is for: `["/security"]`. Left out, it is for every page. See below |
| `steps` | at least one |

A step:

| field | |
|---|---|
| `say` | the sentence, said exactly as written |
| `beats` | the moves hung on its words; may be empty |
| `code` | `{ "title": "agent.ts", "text": "…" }` opens a window of code beside the page; `null` closes it. A step that names none leaves the window as it is |
| `lines` | `[from, to]`, from 1: lights those lines of the window and dims the rest, and the pointer goes to them |

A beat:

| field | |
|---|---|
| `word` | the word of `say` it runs on. Case and punctuation do not count: `"Whitening,"` is `whitening` |
| `do` | the move, below |
| `find` | `[role, name]`: the element, as the page's snapshot names it. Needed by every move but `unhighlight`, `here` and `home` |
| `nth` | which time the word is said in the step, from 1 (the first by default), for a word that repeats |

## The moves

| `do` | |
|---|---|
| `point` | the pointer flies to the element, the face beside it, and rests under its first words. Scrolls first if it is off the screen |
| `highlight` | dims the rest of the page and lights the element, following it as the page scrolls |
| `unhighlight` | takes the light away |
| `scroll_to` | scrolls the page, eased, until the element sits in the upper middle of the screen. A section taller than the screen shows from its start |
| `here` | a ring at the pointer, twice |
| `home` | the pointer goes back to its corner |

A macro never types: a walk shows, and the agent writes into a field only what the visitor said.

## Walks for some pages

A site with several pages usually has a walk for each, and a visitor on `/security` should not be
offered the tour of the home. Name the pages in the file:

```json
{ "name": "keys", "title": "Where your keys live", "pages": ["/security"], "steps": [ … ] }
```

- **The menu** lists only the walks for the page the visitor is on (a trailing slash does not
  matter: `/security` and `/security/` are one page).
- **A call** is the same: the page tells the agent its path, and the agent offers and runs only
  the walks for it. A walk that names no page is for all of them, so name the home's
  walks too (`"pages": ["/"]`) if they are only for the home.
- **A page that never said its path** (an older page) is offered every walk.
- A path is exact: `/developers` is not `/developers/sdk`. List both.

## Naming elements: `find`

`find` is `[role, name]`: the first element of that role whose name *contains* the text (case does
not matter). Roles and names are the accessibility tree's, not the markup's:

| role | what it is | its name |
|---|---|---|
| `region` | a `<section>` with `aria-label` or `aria-labelledby` | that label |
| `heading` | `<h1>`–`<h6>` | its text |
| `article` | `<article>` | its `aria-label` |
| `button`, `link`, `tab` | a `<button>` or `summary`, an `<a href>`, `role="tab"` | its text or `aria-label` |
| `group` | `role="group"`, or `<details>` | its `aria-label` |
| `textbox`, `combobox`, `checkbox`, `radio` | fields | their label |
| `img` | `<img>`, `<figure>` | its `alt` |
| `form` | `<form>` | its `aria-label` |

Three habits keep a walk alive:

1. **Name the parts you point at.** A plain `<div>` has no name, so a macro cannot find it: give
   it `role="group"` and an `aria-label`, or point at its heading instead. This is the whole
   reason a beat "does nothing".
2. **Use a part of the name, not the whole.** `["region", "Pricing"]` finds "Pricing, three plans"
   too; a label you reword later still matches.
3. **A beat that finds nothing is skipped**, quietly, in a walk and in a call. The walk goes on, so a
   renamed section loses a move, not the walk.

## Writing sentences that play well

The sentence is read aloud by the agent's voice, and a walk is recorded once in it.

- **Short sentences, one idea each.** The visitor can stop at any step, and the agent is told how far
  they got.
- **Put the beat on the word that names the thing**, not before it: `"Family"` for "Family Care is
  the one most families pick", so the pointer arrives as the name is said. Avoid a word that is also
  said earlier in the sentence unless you mean it, or give `nth`.
- **Light, then point, then let go.** `highlight` on the first word, `point` a few words later,
  `unhighlight` before you move to a part of the page the light is not on.
- **Write numbers and symbols as you would say them**: "nineteen dollars a month", not "$19/mo".
- **Check it with your ears.** `pinecall walks play plans` plays the recorded walk in the terminal;
  a sentence cut short or a name said strangely is a lexicon entry (`pinecall lexicon`), after which
  that sentence is recorded again.

## What is checked, and when

`macros({ … })` checks every file when the agent's class loads, and refuses one that is not a JSON
object, has no steps, a step that says nothing, a beat that is not `{ word, do, find?, nth? }` or
uses `type`, a word its sentence never says, or `code`/`lines` of the wrong shape. The message names
the macro and the step:

```
macro plans: step 2 never says "Familia"
```

What it cannot check is the page: whether `find` names something that exists. That is found by
running it.

## How the agent runs one

In a call, `runMacro("plans")` sends each step to the page and then says it. The model names a walk
the way it heard it: `runMacro("site tour")` runs `tour` (every word of a macro's name is in what was
asked), and an agent with a single macro runs it whatever it is called. The page binds the step to the reply that
follows and runs each beat as its word is said, by the voice's own timings. When the visitor speaks,
the walk stops and the agent answers them; the result tells it how far it got.

With no call, the page plays the recorded sentence and runs the same beats on the audio's clock,
the words lit as they are said. A call opened after a walk played is told which one and how far, so
the agent goes on from there instead of saying it again.
