/** The screen an agent drew for the caller's page, read out of the call's folded log. */

import { type State } from "./wire/state.js";

/** One part of a screen: the name the agent gave it, what it was given, and what it holds. */
export interface ScreenNode {
  part: string;
  props: Record<string, unknown>;
  children: Screen;
}

/** A whole screen: its parts and the words between them, in order. */
export type Screen = (ScreenNode | string)[];

/** The field of the agent's state a screen travels in. */
const FIELD = "screen";

/** The event a page answers a task with: `call.event(TASK_GIVE, { task, given })`. */
export const TASK_GIVE = "task.give";

/** The screen the agent drew last, or an empty one: before it drew any, and for an agent that draws none. */
export function screenOf(state: State): Screen {
  return read(state.app_state[FIELD]);
}

// What does not read as a part is left out, so a newer agent's screen still draws on an older page.
function read(value: unknown): Screen {
  if (!Array.isArray(value)) return [];
  const screen: Screen = [];
  for (const one of value) {
    if (typeof one === "string") screen.push(one);
    else if (isRecord(one) && typeof one["part"] === "string") {
      screen.push({ part: one["part"], props: isRecord(one["props"]) ? one["props"] : {}, children: read(one["children"]) });
    }
  }
  return screen;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
