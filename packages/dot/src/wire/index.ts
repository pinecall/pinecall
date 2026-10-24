/** What a tutored page and its agent say to each other: the page's events, and the cursor and macro messages it takes. */
//
// Both ride what a call already has. The page's facts go up as events (`call.event(name, data)`,
// the agent's `onEvent`); the agent's moves come down on `pinecall.ui`, beside its cards and
// choices, told apart by `type`.

/** The topic the agent sends on, and the page's `onUi` hears. */
export const UI = "pinecall.ui";

/** The page as the visitor sees it now: `{ text, why }`, sent when it changed; after a move onto an element ended, `why` is `moved` and `at` the ref it moved to, when there was one. */
export const SEEN = "page.seen";
/** The `why` of the `page.seen` that answers a move onto an element. */
export const MOVED = "moved";
/** The visitor clicked something: `{ role, name }`. */
export const CLICKED = "page.clicked";
/** A target the agent named is not on the page: `{ target }`. A fresh `page.seen` follows. */
export const MISSING = "page.missing";

/** What the pointer can do. It never clicks, types or leaves the page for the visitor. */
export const ACTIONS = ["point", "highlight", "unhighlight", "scroll_to", "here", "home"] as const;
export type Action = (typeof ACTIONS)[number];

/** One move of the pointer, as the agent sends it, on `target` for the moves that take one: a ref (`e12`), or a name as the screen shows it (`Questions`). */
export interface Cursor {
  type: "cursor";
  action: Action;
  target?: string | undefined;
}

/** A target that is a ref of the snapshot rather than a name. */
export const A_REF = /^e\d+$/;

/** One move of a macro, run as its word is said. `find` names the element as the snapshot does: `["button", "Book now"]`. */
export interface Beat {
  word: string;
  /** Which time the word is said in the step, from 1; the first by default. */
  nth?: number | undefined;
  do: Action;
  find?: [role: string, name: string] | undefined;
}

/** One sentence of a macro and the moves hung on its words. */
export interface MacroStep {
  say: string;
  beats: Beat[];
}

/** A guided walk an agent was given: `macros/<name>.json` in its folder. */
export interface Macro {
  name: string;
  /** When to run it, in the words the model reads: "the visitor asks to be shown around". */
  when?: string | undefined;
  steps: MacroStep[];
}

/** The agent asking for the page as it is now: sent when its call opens, answered with `page.seen`. */
export interface Look {
  type: "look";
}

/** A step about to be said, sent just before the agent says it. */
export interface Step {
  type: "macro.step";
  macro: string;
  step: number;
  say: string;
  beats: Beat[];
}

const isAction = (value: unknown): value is Action => typeof value === "string" && ACTIONS.some((one) => one === value);
const optionalText = (value: unknown): value is string | undefined => value === undefined || typeof value === "string";

function isBeat(value: unknown): value is Beat {
  if (typeof value !== "object" || value === null) return false;
  const beat: Record<string, unknown> = { ...value };
  const find = beat["find"];
  const found = find === undefined || (Array.isArray(find) && find.length === 2 && find.every((part) => typeof part === "string"));
  const nth = beat["nth"];
  return typeof beat["word"] === "string" && isAction(beat["do"]) && found && (nth === undefined || (typeof nth === "number" && nth >= 1));
}

/** A message on `pinecall.ui` the tutor carries out, or null for one that is not its own (a card, choices). */
export function tutoring(data: unknown): Cursor | Step | Look | null {
  if (typeof data !== "object" || data === null) return null;
  const message: Record<string, unknown> = { ...data };
  if (message["type"] === "look") return { type: "look" };
  if (message["type"] === "cursor" && isAction(message["action"]) && optionalText(message["target"])) {
    return { type: "cursor", action: message["action"], target: message["target"] };
  }
  const beats = message["beats"];
  if (
    message["type"] === "macro.step" &&
    typeof message["macro"] === "string" &&
    typeof message["step"] === "number" &&
    typeof message["say"] === "string" &&
    Array.isArray(beats) &&
    beats.every(isBeat)
  ) {
    return { type: "macro.step", macro: message["macro"], step: message["step"], say: message["say"], beats };
  }
  return null;
}

/** A macro as its JSON file says it, checked; it throws naming what is wrong, at the class's load. */
export function macroOf(name: string, value: unknown): Macro {
  if (typeof value !== "object" || value === null) throw new Error(`macro ${name}: not a JSON object`);
  const macro: Record<string, unknown> = { ...value };
  const steps = macro["steps"];
  if (!Array.isArray(steps) || steps.length === 0) throw new Error(`macro ${name}: no steps`);
  const checked = steps.map((step: unknown, at) => {
    if (typeof step !== "object" || step === null) throw new Error(`macro ${name}: step ${at + 1} is not an object`);
    const fields: Record<string, unknown> = { ...step };
    const say = fields["say"];
    const beats = fields["beats"] ?? [];
    if (typeof say !== "string" || say.trim() === "") throw new Error(`macro ${name}: step ${at + 1} says nothing`);
    if (!Array.isArray(beats) || !beats.every(isBeat)) throw new Error(`macro ${name}: step ${at + 1} has a beat that is not {word, do, find?, nth?}`);
    for (const beat of beats) {
      if (!wordsOf(say).some((word) => word === normal(beat.word))) throw new Error(`macro ${name}: step ${at + 1} never says "${beat.word}"`);
    }
    return { say, beats };
  });
  const when = macro["when"];
  return { name: typeof macro["name"] === "string" ? macro["name"] : name, when: typeof when === "string" ? when : undefined, steps: checked };
}

/** A word as two texts are compared: lower case, letters and digits alone. */
export function normal(word: string): string {
  return word.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

/** A sentence's words, normalised, the empty ones left out. */
export function wordsOf(text: string): string[] {
  return text.split(/\s+/).map(normal).filter((word) => word !== "");
}
