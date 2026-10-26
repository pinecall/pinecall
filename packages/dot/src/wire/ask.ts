/** What the dot asks when the visitor types to it, and the one thing it may be told to do: a walk, a thing shown, the agent, or nothing. */
//
// The visitor types "where do I see what each plan includes?" and the dot does something on the page,
// never a conversation: it plays one of the page's walks, shows one thing of the page, offers the agent
// for a question a person answers, or says it cannot find it. What decides is a server's (`@pinecall/dot/server`);
// this is what the two say to each other. A walk that takes params is told them, picked out of what was typed.
// The same door picks the row of a table a walk read that best answers the visitor, and records a sentence
// of a walk once its slots are filled: one door, three asks, told apart by their one key.

import { LONGEST_VALUE, type Values } from "./acts.js";

/** What the visitor typed, and the page it was typed on, as the dot sends it to be decided. */
export interface AskRequest {
  message: string;
  /** The path of the page: `/pricing`. */
  path: string;
  /** The page as the agent reads it: each thing with its role, its name and its ref. */
  page: string;
  /** The walks of this page, and what each takes. */
  walks: { name: string; title: string; when?: string | undefined; params?: Record<string, { about: string; oneOf?: Record<string, string> | undefined }> | undefined }[];
}

/** Which row of a table a walk read best answers what the visitor typed: each row as its cells, joined. */
export interface RowRequest {
  message: string;
  rows: string[];
}

/** A sentence of a walk with slots, to record now its values are known: the page it is on, the walk, the step, the values. */
export interface SayRequest {
  path: string;
  walk: string;
  step: number;
  values: Values;
}

/** A text of the page itself to record in the agent's voice: a part of a page read aloud. */
export interface ReadRequest {
  text: string;
}

/** What the page asks the site's door: one of the four. */
export type DoorRequest = { decide: AskRequest } | { row: RowRequest } | { say: SayRequest } | { read: ReadRequest };

/** The site's door's answer to a `row`: the row's index, or null when none answers it. */
export interface RowAnswer {
  row: number | null;
}

/** The door's answer to a `say`: the sentence as recorded. */
export interface SaidAnswer {
  say: string;
  audio: string;
  durationMs: number;
  words: { text: string; startMs: number; endMs: number }[];
}

/** The one thing to do, and how sure the decision is, 0 to 1. */
export type Decision =
  | { do: "walk"; walk: string; params?: Values | undefined; confidence: number }
  | { do: "show"; target: string; confidence: number }
  | { do: "talk"; confidence: number }
  | { do: "none"; confidence: number };

/** A thing of the page with a name: its ref, its role and its name. */
export interface Named {
  ref: string;
  role: string;
  name: string;
}

// A line of the page as Page writes it: `  - heading "Pricing" [level=2] [ref=e10]`. A name's own quotes are
// written as apostrophes, so the first closing quote ends it.
const A_THING = /^\s*- ([a-z]+) "([^"]*)".*?\[ref=(e\d+)\]/;

/** The things of a page with a name and a ref, in the page's order. */
export function namedIn(page: string): Named[] {
  return page.split("\n").flatMap((line) => {
    const found = A_THING.exec(line);
    return found === null || found[2] === undefined || found[2].trim() === "" ? [] : [{ role: found[1] ?? "", name: found[2], ref: found[3] ?? "" }];
  });
}

const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/** A decision as a server answered it, checked; null for anything else. */
export function decisionOf(value: unknown): Decision | null {
  if (typeof value !== "object" || value === null) return null;
  const fields: Record<string, unknown> = { ...value };
  const confidence = fields["confidence"];
  if (!isNumber(confidence)) return null;
  switch (fields["do"]) {
    case "walk": {
      if (typeof fields["walk"] !== "string") return null;
      const given = fields["params"];
      if (given === undefined) return { do: "walk", walk: fields["walk"], confidence };
      if (typeof given !== "object" || given === null) return null;
      const params = Object.fromEntries(Object.entries(given).filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1].length <= LONGEST_VALUE));
      return { do: "walk", walk: fields["walk"], params, confidence };
    }
    case "show":
      return typeof fields["target"] === "string" && /^e\d+$/.test(fields["target"]) ? { do: "show", target: fields["target"], confidence } : null;
    case "talk":
      return { do: "talk", confidence };
    case "none":
      return { do: "none", confidence };
    default:
      return null;
  }
}

/** A row answer, checked; null for anything else. */
export function rowOf(value: unknown): number | null {
  if (typeof value !== "object" || value === null) return null;
  const row = (value as Record<string, unknown>)["row"];
  return typeof row === "number" && Number.isInteger(row) && row >= 0 ? row : null;
}

/** A recorded sentence, checked; null for anything else. */
export function saidOf(value: unknown): SaidAnswer | null {
  if (typeof value !== "object" || value === null) return null;
  const said: Record<string, unknown> = { ...value };
  const { say, audio, durationMs, words } = said;
  if (typeof say !== "string" || typeof audio !== "string" || !/^https?:\/\//.test(audio) || typeof durationMs !== "number" || !Array.isArray(words)) return null;
  const timed = words.filter((word): word is SaidAnswer["words"][number] => {
    if (typeof word !== "object" || word === null) return false;
    const one: Record<string, unknown> = { ...word };
    return typeof one["text"] === "string" && typeof one["startMs"] === "number" && typeof one["endMs"] === "number";
  });
  return timed.length === words.length ? { say, audio, durationMs, words: timed } : null;
}
