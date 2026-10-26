/** A macro as a function: the params it takes, the steps that act on the page (fill, press, wait, read), and the `{slots}` its words are filled from. */
//
// A walk that takes params is called with them: in a call the agent's model passes them, with no call
// the site's server picks them out of what the visitor typed (`@pinecall/dot/server`). A param is the
// visitor's own words (a name, a phone, what to search for) or one option of a list. Its value fills
// the `{name}` slots of the walk's sentences and of what a step types, and `read` adds the cells of a
// row of a table the page shows (`{hit.Time}`). A step with a slot nothing filled is left out, so a
// walk said without a param says the rest; `if` and `unless` keep a step for a value there, or not.

/** What a walk is called with, or read on its way: each slot's text. */
export type Values = Record<string, string>;

/** One param of a walk: what it is, in the words the model reads, and the options it is one of; none, the visitor's own words. */
export interface Param {
  about: string;
  oneOf?: Record<string, string> | undefined;
}

/** Type the filled `with` into the field the screen names `fill`: the visitor's words, never a password or a card. */
export interface FillAct {
  fill: string;
  with: string;
}

/** Press the button the screen names `press`: one outside any form, or in a search form. Never a slot: the site names it. */
export interface PressAct {
  press: string;
}

/** Wait for the page to change after a press, a search answered: `ms` at most, 8 seconds when not said. */
export interface WaitAct {
  wait: string;
  ms?: number | undefined;
}

/** Read the table the screen names `read`: one row, the first or the one that best answers the visitor, its cells as `{as.Column}`. */
export interface ReadAct {
  read: string;
  as: string;
  row?: "first" | "best" | undefined;
}

export type Act = FillAct | PressAct | WaitAct | ReadAct;

/** When a step is taken: `if` a slot has a value, `unless` it has one. */
export interface Guarded {
  if?: string | undefined;
  unless?: string | undefined;
}

/** The longest a wait may be, in ms. */
export const LONGEST_WAIT = 20_000;
/** The longest a value may be: a name, a phone, a cell. */
export const LONGEST_VALUE = 80;

const SLOT = /\{([A-Za-z_][\w]*(?:\.[^{}\n]+)?)\}/g;

/** The slots a text names, in order: `{name}`, `{hit.Time}`. */
export function slotsOf(text: string): string[] {
  return [...text.matchAll(SLOT)].map((found) => found[1] ?? "");
}

/** `text` with its slots filled; null when one has no value. */
export function filled(text: string, values: Values): string | null {
  let missing = false;
  const out = text.replace(SLOT, (_, slot: string) => {
    const value = values[slot];
    if (value === undefined || value === "") missing = true;
    return value ?? "";
  });
  return missing ? null : out;
}

/** Whether a step is taken, with these values. */
export function taken(step: Guarded, values: Values): boolean {
  const has = (slot: string): boolean => (values[slot] ?? "") !== "";
  return (step.if === undefined || has(step.if)) && (step.unless === undefined || !has(step.unless));
}

/** A value as it may fill a slot: one line, cut. */
export function valueOf(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, LONGEST_VALUE);
}

/** Whether a step is an act rather than a sentence. */
export function isAct(step: object): step is Act {
  return "fill" in step || "press" in step || "wait" in step || "read" in step;
}

const text = (value: unknown): value is string => typeof value === "string" && value.trim() !== "";

/** An act as a file or a document says it, checked; null for one that is not. */
export function actOf(fields: Record<string, unknown>): Act | null {
  if ("fill" in fields) return text(fields["fill"]) && text(fields["with"]) ? { fill: fields["fill"], with: fields["with"] } : null;
  if ("press" in fields) return text(fields["press"]) && slotsOf(fields["press"]).length === 0 ? { press: fields["press"] } : null;
  if ("wait" in fields) {
    const ms = fields["ms"];
    if (!text(fields["wait"]) || (ms !== undefined && (typeof ms !== "number" || ms <= 0 || ms > LONGEST_WAIT))) return null;
    return { wait: fields["wait"], ...(ms === undefined ? {} : { ms }) };
  }
  if ("read" in fields) {
    const row = fields["row"];
    if (!text(fields["read"]) || !text(fields["as"]) || !/^[A-Za-z_]\w*$/.test(fields["as"])) return null;
    if (row !== undefined && row !== "first" && row !== "best") return null;
    return { read: fields["read"], as: fields["as"], ...(row === undefined ? {} : { row }) };
  }
  return null;
}

/** A step's guards, checked; null when one is not a slot's name. */
export function guardsOf(fields: Record<string, unknown>): Guarded | null {
  const guards: Guarded = {};
  for (const key of ["if", "unless"] as const) {
    const slot = fields[key];
    if (slot === undefined) continue;
    if (typeof slot !== "string" || slot === "") return null;
    guards[key] = slot;
  }
  return guards;
}

/** A walk's params, as its file or document says them (`one_of` for the options), checked; null for any that is not one. */
export function paramsOf(value: unknown): Record<string, Param> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const params: Record<string, Param> = {};
  for (const [name, declared] of Object.entries(value)) {
    if (!/^[A-Za-z_]\w*$/.test(name) || typeof declared !== "object" || declared === null) return null;
    const fields: Record<string, unknown> = { ...declared };
    const about = fields["about"];
    const options = fields["one_of"] ?? fields["oneOf"];
    if (!text(about)) return null;
    if (options === undefined) {
      params[name] = { about };
      continue;
    }
    if (typeof options !== "object" || options === null || Array.isArray(options)) return null;
    const entries = Object.entries(options);
    if (entries.length === 0 || !entries.every(([, said]) => typeof said === "string")) return null;
    params[name] = { about, oneOf: Object.fromEntries(entries) as Record<string, string> };
  }
  return params;
}

/** The values a walk is called with, checked against its params: a list's value one of its options, the rest the visitor's words, cut. */
export function valuesFor(params: Record<string, Param>, given: Record<string, unknown>): { values: Values; wrong: string[] } {
  const values: Values = {};
  const wrong: string[] = [];
  for (const [name, value] of Object.entries(given)) {
    const param = params[name];
    if (param === undefined || typeof value !== "string" || value.trim() === "") continue;
    if (param.oneOf !== undefined && !(value in param.oneOf)) {
      wrong.push(`${name} is one of ${Object.keys(param.oneOf).join(", ")}`);
      continue;
    }
    values[name] = valueOf(value);
  }
  return { values, wrong };
}
