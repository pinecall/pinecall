// The judges a class owns and the callers its test folder holds: `ownJudge`, `ownPersona`, `judges({ on, own })`, `personas({ on, own })`, `rosterIn`.

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
  const made = toCamel(parsed.data);
  Object.defineProperty(made, MADE, { value: true });
  return made;
}

// The mark `ownPersona` leaves on what it made, so a file's callers are told from whatever else it exports. Asked of the
// symbol registry and never listed among the caller's own keys: it is the same mark in a second copy of this package,
// and nothing that reads or sends a caller meets it.
const MADE = Symbol.for("pinecall.ownPersona");

// The roster read from the file beside each class's goldens, by class.
const BESIDE = new WeakMap<Function, NonNullable<Declared["personas"]>>();

/** What a served agent is told once when its class still names its callers: they play, and their place is the file. */
export const CALLERS_MOVED =
  "its personas are declared in the class, which still works: their place is now test/personas.ts beside the goldens — every ownPersona it exports is the agent's own, and `on` names Pinecall's";

/**
 * The roster a `test/personas.ts` holds: every `ownPersona` it exports is one of the agent's own, and its
 * `on` names the ones of Pinecall's its runs play. Whatever else it exports is not a caller, and is left alone.
 */
export function rosterIn(exported: Record<string, unknown>, file: string): NonNullable<Declared["personas"]> {
  const on = exported["on"] ?? [];
  if (!Array.isArray(on) || on.some((name) => typeof name !== "string")) throw new DeclarationRefused(`${file}: on is the names of Pinecall's callers the agent is tested with, a list of strings`);
  const own = Object.values(exported).filter((one): one is OwnPersona => typeof one === "object" && one !== null && (one as { [MADE]?: true })[MADE] === true);
  return personas({ on: on as string[], own });
}

/** The class is tested with the roster its `test/personas.ts` holds; one that names its callers too is refused. */
export function testedWith(ctor: Function, roster: NonNullable<Declared["personas"]>, file: string): void {
  if (namesItsCallers(ctor)) throw new DeclarationRefused(`${ctor.name} declares personas in @agent({ … }) and ${file} holds them too: the file is their place — take personas out of the class`);
  BESIDE.set(ctor, roster);
}

/** Whether the class names its callers itself, the old place for them. */
export function namesItsCallers(ctor: Function): boolean {
  const declared = (ctor as unknown as { personas?: Declared["personas"] }).personas;
  return declared !== undefined && declared !== null;
}

/** The judges the class owns: which of Pinecall's its calls meet (`on`), and its own (`own`, each an `ownJudge`). */
export function judges(options: { on?: string[] | undefined; own?: OwnJudge[] | undefined } = {}): NonNullable<Declared["judges"]> {
  return { on: [...(options.on ?? [])], own: eachOnce("judge", (options.own ?? []).map((one) => ownJudge(judgeInputOf(one)))) };
}

/** The personas the class owns: which of Pinecall's its runs play (`on`), and its own (`own`, each an `ownPersona`). */
export function personas(options: { on?: string[] | undefined; own?: OwnPersona[] | undefined } = {}): NonNullable<Declared["personas"]> {
  return { on: [...(options.on ?? [])], own: eachOnce("persona", (options.own ?? []).map(ownPersona)) };
}

/**
 * The judges a class declares and the callers it is tested with, as the declaration sends them; nothing for a class
 * with neither. The callers are the file's, or the class's own for one that still names them and has no file.
 */
export function harnessOf(ctor: Function): Harness {
  const declared = ctor as unknown as { judges?: Declared["judges"]; personas?: Declared["personas"] };
  const harness: Harness = {};
  if (declared.judges !== undefined && declared.judges !== null) harness.judges = judges(declared.judges);
  const beside = BESIDE.get(ctor);
  if (beside !== undefined) harness.personas = beside;
  else if (declared.personas !== undefined && declared.personas !== null) harness.personas = personas(declared.personas);
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
