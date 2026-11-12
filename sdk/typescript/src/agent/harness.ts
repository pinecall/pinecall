// The judges and the personas a class owns: `ownJudge`, `ownPersona`, and `judges({ on, own })`, `personas({ on, own })`.

import { PersonaDeclarationSchema, type AgentConfig, type JudgeDeclaration, type PersonaDeclaration } from "../wire/agent-config.js";
import { toCamel, toSnake, type Camel } from "../wire/codec.js";
import { DeclarationRefused } from "./tools.js";

type Declared = Camel<AgentConfig>;

/** What the class owns of its harness, as the declaration sends it. */
export type Harness = Pick<Declared, "judges" | "personas">;

/** One judge of the agent's own, as the declaration carries it. */
export type OwnJudge = Camel<JudgeDeclaration>;
/** One caller of the agent's own, as the declaration carries it. */
export type OwnPersona = Camel<PersonaDeclaration>;

/** What `ownJudge` takes: the name, the question it asks of a call, and how and when it answers. */
export interface JudgeInput {
  /** Lower-case words joined by hyphens: `offers-next-slot`. */
  name: string;
  /** The one sentence the judge model answers about the finished call. */
  asks: string;
  /** `verdict` (held or broken, the default), `score` (1 to 5), or `choice` (one of `choices`). */
  answer?: OwnJudge["answer"];
  /** Two at least, and only for `choice`. */
  choices?: string[];
  /** `always` (the default), `simulations`, or `trigger` (asked only when `trigger` is answered yes). */
  when?: OwnJudge["when"];
  trigger?: string;
  /** What the judge reads beyond the call: `prompt`, `evidence`, `facts`. */
  reads?: OwnJudge["reads"];
}

/** The name a judge or a persona is called by: lower-case words joined by hyphens. */
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const ANSWERS = ["verdict", "choice", "score"] as const;
const WHENS = ["always", "simulations", "trigger"] as const;
const READS = ["prompt", "evidence", "facts"] as const;

/** A judge of the agent's own, refused by sentence when it is wrong; `own: [...]` of `judges()` takes it. */
export function ownJudge(input: JudgeInput): OwnJudge {
  const { name } = input;
  if (typeof name !== "string" || !A_NAME.test(name)) throw new DeclarationRefused(`"${String(name)}" is not a judge's name: lower-case words joined by hyphens, like offers-next-slot`);
  const question = typeof input.asks === "string" ? input.asks.trim() : "";
  if (question === "") throw new DeclarationRefused(`${name}: a judge asks a question of a call: write it as asks`);
  const answer = oneOf(name, "answer", input.answer ?? "verdict", ANSWERS);
  const choices = [...(input.choices ?? [])];
  if (answer === "choice" && choices.length < 2) throw new DeclarationRefused(`${name}: a judge that answers one of several needs at least two choices`);
  if (answer !== "choice" && choices.length > 0) throw new DeclarationRefused(`${name}: only a judge that answers one of several takes choices`);
  const when = oneOf(name, "when", input.when ?? "always", WHENS);
  const trigger = input.trigger ?? "";
  if (when === "trigger" && trigger.trim() === "") throw new DeclarationRefused(`${name}: a judge that runs on a trigger needs the trigger's question`);
  const reads = (input.reads ?? []).map((read) => oneOf(name, "reads", read, READS));
  return { name, question, answer, choices, when, trigger, reads };
}

/** A caller of the agent's own — what `PUT …/personas/{name}` takes — refused by sentence when it is wrong. */
export function ownPersona(input: OwnPersona): OwnPersona {
  const { name } = input;
  if (typeof name !== "string" || !A_NAME.test(name)) throw new DeclarationRefused(`"${String(name)}" is not a persona's name: lower-case words joined by hyphens, like price-shopper`);
  if (typeof input.goal !== "string" || input.goal.trim() === "") throw new DeclarationRefused(`${name}: a persona wants something: write its goal, in the first person`);
  if (typeof input.style !== "string" || input.style.trim() === "") throw new DeclarationRefused(`${name}: a persona talks some way: write its style`);
  const parsed = PersonaDeclarationSchema.safeParse(toSnake(input));
  if (!parsed.success) throw new DeclarationRefused(`${name}: ${parsed.error.issues.map((issue) => `${issue.path.join(".") || "it"}: ${issue.message}`).join("; ")}`);
  return toCamel(parsed.data);
}

/** The judges the class owns: which of Pinecall's its calls meet (`on`), and its own (`own`, each an `ownJudge`). */
export function judges(options: { on?: string[] | undefined; own?: OwnJudge[] | undefined } = {}): NonNullable<Declared["judges"]> {
  return { on: [...(options.on ?? [])], own: eachOnce("judge", (options.own ?? []).map((one) => ownJudge(judgeInputOf(one)))) };
}

/** The personas the class owns: which of Pinecall's its runs play (`on`), and its own (`own`, each an `ownPersona`). */
export function personas(options: { on?: string[] | undefined; own?: OwnPersona[] | undefined } = {}): NonNullable<Declared["personas"]> {
  return { on: [...(options.on ?? [])], own: eachOnce("persona", (options.own ?? []).map(ownPersona)) };
}

/** The judges and the personas a class declares, as the declaration sends them; nothing for a class that declares neither. */
export function harnessOf(ctor: Function): Harness {
  const declared = ctor as unknown as { judges?: Declared["judges"]; personas?: Declared["personas"] };
  const harness: Harness = {};
  if (declared.judges !== undefined && declared.judges !== null) harness.judges = judges(declared.judges);
  if (declared.personas !== undefined && declared.personas !== null) harness.personas = personas(declared.personas);
  return harness;
}

// A judge already built reads back as its input, so `judges()` checks it the same way once more.
function judgeInputOf(one: OwnJudge): JudgeInput {
  return { name: one.name, asks: one.question, answer: one.answer ?? "verdict", choices: one.choices ?? [], when: one.when ?? "always", trigger: one.trigger ?? "", reads: one.reads ?? [] };
}

function eachOnce<T extends { name: string }>(what: string, own: T[]): T[] {
  const seen = new Set<string>();
  for (const one of own) {
    if (seen.has(one.name)) throw new DeclarationRefused(`two ${what}s called ${one.name}: a name is declared once`);
    seen.add(one.name);
  }
  return own;
}

function oneOf<T extends string>(name: string, field: string, value: string, allowed: readonly T[]): T {
  const found = allowed.find((each) => each === value);
  if (found === undefined) throw new DeclarationRefused(`${name}: ${field} is "${value}", not one of ${allowed.join(", ")}`);
  return found;
}
