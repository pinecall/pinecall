// The judges and the personas a class owns: `judges({ on })`, `personas({ on })`, and the folders beside the class read.

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

import { PersonaDeclarationSchema, type AgentConfig, type JudgeDeclaration, type PersonaDeclaration } from "../wire/agent-config.js";
import { toCamel, type Camel } from "../wire/codec.js";
import { DeclarationRefused } from "./tools.js";

type Declared = Camel<AgentConfig>;

/** What the class owns of its harness, as the declaration sends it. */
export type Harness = Pick<Declared, "judges" | "personas">;

/** The name a judge or a persona is called by: lower-case words joined by hyphens. */
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const ANSWERS = ["verdict", "choice", "score"] as const;
const WHENS = ["always", "simulations", "trigger"] as const;
const READS = ["prompt", "evidence", "facts"] as const;

/** The judges the class owns: which of Pinecall's its calls meet. Its own are the files under `judges/`. */
export function judges(options: { on?: string[] } = {}): NonNullable<Declared["judges"]> {
  return { on: [...(options.on ?? [])] };
}

/** The personas the class owns: which of Pinecall's its runs play. Its own are the files under `test/personas/`. */
export function personas(options: { on?: string[] } = {}): NonNullable<Declared["personas"]> {
  return { on: [...(options.on ?? [])] };
}

/**
 * What `static judges` and `static personas` declare, with the folders beside the class read into
 * `own`. A folder with files and no declaration is refused: a judge nobody declared would run on
 * no call, and the sentence says what to write.
 */
export function harnessOf(ctor: Function, file?: string): Harness {
  const declared = ctor as unknown as { judges?: Declared["judges"]; personas?: Declared["personas"] };
  const dir = file === undefined ? undefined : dirname(resolve(file));
  const harness: Harness = {};
  const judgeFiles = dir === undefined ? [] : readJudgeFiles(join(dir, "judges"));
  if (declared.judges !== undefined && declared.judges !== null) {
    harness.judges = { on: [...(declared.judges.on ?? [])], own: [...(declared.judges.own ?? []), ...judgeFiles] };
  } else if (judgeFiles.length > 0) {
    throw new DeclarationRefused(`${join(dir ?? "", "judges")} holds ${judgeFiles.length} judge(s) and the class declares none: static judges = judges({ on: ["consent", …] }) declares them, and which of Pinecall's run`);
  }
  const personaFiles = dir === undefined ? [] : readPersonaFiles(join(dir, "test", "personas"));
  if (declared.personas !== undefined && declared.personas !== null) {
    harness.personas = { on: [...(declared.personas.on ?? [])], own: [...(declared.personas.own ?? []), ...personaFiles] };
  } else if (personaFiles.length > 0) {
    throw new DeclarationRefused(`${join(dir ?? "", "test", "personas")} holds ${personaFiles.length} persona(s) and the class declares none: static personas = personas({ on: ["in-a-hurry", …] }) declares them, and which of Pinecall's play`);
  }
  return harness;
}

/** Every `<name>.md` under the folder as a judge, each refused by sentence; none for no folder. */
export function readJudgeFiles(folder: string): Camel<JudgeDeclaration>[] {
  return files(folder, ".md").map((path) => judgeOf(path, readFileSync(path, "utf8")));
}

/** Every `<name>.json` under the folder as a persona, each refused by sentence; none for no folder. */
export function readPersonaFiles(folder: string): Camel<PersonaDeclaration>[] {
  return files(folder, ".json").map((path) => personaOf(path, readFileSync(path, "utf8")));
}

function files(folder: string, extension: string): string[] {
  if (!existsSync(folder)) return [];
  return readdirSync(folder)
    .filter((name) => name.endsWith(extension))
    .sort()
    .map((name) => join(folder, name));
}

/** A judge file: the library's own format, front matter between two `---` lines and the question below. */
export function judgeOf(path: string, text: string): Camel<JudgeDeclaration> {
  const shown = basename(path);
  const name = basename(path, ".md");
  const [fields, body] = page(shown, text);
  if (!A_NAME.test(name)) throw new DeclarationRefused(`${shown}: "${name}" is not a judge's name: lower-case words joined by hyphens, like offers-next-slot`);
  if (fields["name"] !== undefined && fields["name"] !== name) {
    throw new DeclarationRefused(`${shown}: its front matter says name: ${fields["name"]}, and the file is ${shown}: the file's name is the judge's`);
  }
  const question = body.trim();
  if (question === "") throw new DeclarationRefused(`${shown}: a judge asks a question of a call: write one below the front matter`);
  const answer = oneOf(shown, "answer", fields["answer"] ?? "verdict", ANSWERS);
  const choices = listed(fields["choices"] ?? "");
  if (answer === "choice" && choices.length < 2) throw new DeclarationRefused(`${shown}: a judge that answers one of several needs at least two choices`);
  if (answer !== "choice" && choices.length > 0) throw new DeclarationRefused(`${shown}: only a judge that answers one of several takes choices`);
  const when = oneOf(shown, "when", fields["when"] ?? fields["on"] ?? "always", WHENS);
  const trigger = fields["trigger"] ?? "";
  if (when === "trigger" && trigger.trim() === "") throw new DeclarationRefused(`${shown}: a judge that runs on a trigger needs the trigger's question`);
  const reads = listed(fields["reads"] ?? "").map((read) => oneOf(shown, "reads", read, READS));
  return { name, question, answer, choices, when, trigger, reads };
}

/** A persona file: JSON, what `PUT …/personas/{name}` takes, the name being the file's. */
export function personaOf(path: string, text: string): Camel<PersonaDeclaration> {
  const shown = basename(path);
  const name = basename(path, ".json");
  if (!A_NAME.test(name)) throw new DeclarationRefused(`${shown}: "${name}" is not a persona's name: lower-case words joined by hyphens, like price-shopper`);
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (error) {
    throw new DeclarationRefused(`${shown}: not JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) throw new DeclarationRefused(`${shown}: a persona is a JSON object with a goal and a style`);
  const given = raw as Record<string, unknown>;
  if (typeof given["goal"] !== "string" || given["goal"].trim() === "") throw new DeclarationRefused(`${shown}: a persona wants something: write its goal, in the first person`);
  if (typeof given["style"] !== "string" || given["style"].trim() === "") throw new DeclarationRefused(`${shown}: a persona talks some way: write its style`);
  if (given["name"] !== undefined && given["name"] !== name) throw new DeclarationRefused(`${shown}: it says its name is ${String(given["name"])}, and the file is ${shown}: the file's name is the persona's`);
  const parsed = PersonaDeclarationSchema.safeParse({ ...given, name });
  if (!parsed.success) throw new DeclarationRefused(`${shown}: ${parsed.error.issues.map((issue) => `${issue.path.join(".") || "it"}: ${issue.message}`).join("; ")}`);
  return toCamel(parsed.data);
}

function page(shown: string, text: string): [Record<string, string>, string] {
  const opened = text.indexOf("---\n");
  const closed = opened === -1 ? -1 : text.indexOf("\n---\n", opened + 4);
  if (opened === -1 || closed === -1) throw new DeclarationRefused(`${shown}: a judge opens with its front matter between two --- lines, and the question below`);
  const fields: Record<string, string> = {};
  for (const line of text.slice(opened + 4, closed).split("\n")) {
    const at = line.indexOf(":");
    if (at === -1 || line.trim() === "") continue;
    fields[line.slice(0, at).trim()] = line.slice(at + 1).replace(/\s+#.*$/, "").trim();
  }
  return [fields, text.slice(closed + 5)];
}

// A list is `[a, b]` or `a, b`; the library writes the second.
function listed(value: string): string[] {
  return value
    .replace(/^\[|\]$/g, "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "");
}

function oneOf<T extends string>(shown: string, field: string, value: string, allowed: readonly T[]): T {
  const found = allowed.find((each) => each === value);
  if (found === undefined) throw new DeclarationRefused(`${shown}: ${field} is "${value}", not one of ${allowed.join(", ")}`);
  return found;
}
