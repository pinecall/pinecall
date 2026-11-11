# The screen the agent draws

An agent written with `@pinecall/agents` may draw the caller's page: its `screen()` returns parts by name,
each with plain data, and the call's log carries them. `screenOf` reads the screen the agent drew last, and
`<Screen>` draws it with one component of yours per part.

```tsx
import { screenOf, TASK_GIVE } from "@pinecall/room";
import { Screen, useRoom, type Parts } from "@pinecall/room/react";

const PARTS: Parts = {
  agenda: ({ slots }) => slots.map((slot) => <button onClick={() => call.event("slot.picked", slot)}>{slot.time}</button>),
  form: ({ task }) => <PhoneForm onGive={(number) => call.event(TASK_GIVE, { task, given: { number } })} />,
  ticket: Ticket,
};

<Screen screen={screenOf(call.log)} parts={PARTS} />;
```

A part's props are what the agent gave it, and what it holds arrives as `children`. A part the page has no
component for is not drawn, and `onUnknown` is told its name. The screen is a public field of the call's
state, so it is there in every mode, a phone call the page follows included, and it is still there after
the call ended. Without React, `screenOf(state.log)` is the tree: `{ part, props, children }` and the words
between them.

`TASK_GIVE` (`"task.give"`) is the event a page answers a task with, when the agent's screen shows what a
tool stopped to ask for: `{ task, given }`, where `given` holds the task's fields.
