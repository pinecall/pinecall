/** What a class declares of its environment: `@voice`, `@llm`, `@realtime`, `@stt`, `@judge` and its static fields. */

import { improvise, type Ending, type Opening } from "../agent/opening.js";
import { DeclarationRefused } from "../agent/tools.js";
import type { AgentOptions } from "../client/agent.js";

/** The settings a class may declare. Whatever it declares wins over the agent's settings. */
export const ENVIRONMENT = [
  "language",
  "voice",
  "llm",
  "realtime",
  "stt",
  "judge",
  "greeting",
  "hangup",
  "turn",
  "says",
  "hears",
  "knowledge",
  "docs",
  "memory",
  "record",
] as const;

type Environment = Pick<AgentOptions, (typeof ENVIRONMENT)[number]>;

const NOT_AN_OPENING = "a greeting is the words, as a string, or improvise for the model's own: improvise(\"…\") gives it an instruction";
const NOT_AN_ENDING = "hangup is when the model may end the call, in your words, or true whenever it judges the call done";

const DECORATED: Readonly<Record<string, string>> = {
  voice: "@voice('<vendor>', '<voice id>')",
  llm: "@llm('<vendor>/<model>')",
  realtime: "@realtime('<vendor>/<model>')",
  stt: "@stt('<vendor>/<model>')",
  judge: "@judge('<vendor>/<model>')",
};

/** The error message for an environment field declared on the instance. */
export function declaredOnTheInstance(field: string): string {
  const way = DECORATED[field] ?? `static ${field} = …`;
  return `\`${field}\` is the class's, not a call's state: declare it as ${way}`;
}

/** The environment the class declares, as the declaration sends it. */
export function environmentOf(ctor: Function): Environment {
  const declared = ctor as unknown as Record<string, unknown>;
  const environment: Record<string, unknown> = {};
  for (const field of ENVIRONMENT) {
    if (declared[field] !== undefined) environment[field] = declared[field];
  }
  if (environment["greeting"] !== undefined) environment["greeting"] = greetingOf(environment["greeting"] as Opening);
  if (environment["hangup"] !== undefined) environment["hangup"] = hangupOf(environment["hangup"] as Ending);
  return environment as Environment;
}

/** An opening as the wire says it: words to `say`, or a `reply` the model opens on, empty for its prompt alone. */
function greetingOf(opening: Opening): Environment["greeting"] {
  if (opening === improvise) return { reply: "" };
  if (typeof opening === "string") return { say: opening };
  if (typeof opening !== "object" || opening === null) throw new DeclarationRefused(NOT_AN_OPENING);
  if ("text" in opening) return { say: opening.text, ...interruptible(opening.interruptible) };
  if ("improvise" in opening) return { reply: opening.improvise, ...interruptible(opening.interruptible) };
  throw new DeclarationRefused(NOT_AN_OPENING);
}

/** When the model may end the call, as the wire says it: an empty `when` is whenever it judges. */
function hangupOf(ending: Ending): Environment["hangup"] {
  if (ending === true) return { when: "" };
  if (typeof ending === "string" && ending.trim() !== "") return { when: ending };
  throw new DeclarationRefused(NOT_AN_ENDING);
}

function interruptible(given: boolean | undefined): { allowInterruptions?: boolean } {
  return given === undefined ? {} : { allowInterruptions: given };
}

/** Throw on the first environment field the instance declares, where it would be the call's state. */
export function refuseTheEnvironment(probe: object): void {
  for (const field of ENVIRONMENT) {
    if (Object.hasOwn(probe, field)) throw new DeclarationRefused(declaredOnTheInstance(field));
  }
}
