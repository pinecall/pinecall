/** The agent's harness file: its own judges and callers as code, in its language, one more appended by `pull`, `generate --save` and the console. */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";

import { UsageError } from "../errors.js";
import { FRAMEWORK, HARNESS_FILES, languageOf, TEMPLATE_ROOT, type Language } from "./language.js";
import { titleOf, type AgentHome } from "./layout.js";

/** A judge as the gateway keeps one, what `ownJudge` takes with `question` as `asks`. */
export interface JudgeWritten {
  name: string;
  question: string;
  answer: string;
  choices: string[];
  when: string;
  trigger: string;
  reads: string[];
}

/** A caller as the gateway keeps one: what `PUT …/personas/{name}` takes, with its name. */
export interface PersonaWritten {
  name: string;
  about?: string;
  goal: string;
  style: string;
  facts?: Record<string, string>;
  state?: object;
  expects?: string[];
  tags?: string[];
  behavior?: object;
  llm?: string | null;
  tts?: string | null;
  voice?: string | null;
}

/** What was written: the file, relative to the project's root, and the name the code declares it under. */
export interface Appended {
  path: string;
  symbol: string;
}

// Mirrors the gateway's name rule so a bad name gets a readable error.
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

// How a caller acts when the code says nothing: only what differs from this is written into it.
const BEHAVIOR_DEFAULTS: Record<string, unknown> = { interrupts: 0, pause_s: 0, interferer_db: null, packet_loss: 0, backchannels: 0, speed: 1, ambience: "television" };

export const NOT_A_NAME = (name: string): string => `${name} is no name for one of the agent's own: lower-case letters and digits joined by hyphens — apurado, price-shopper`;
export const DECLARED_ALREADY = (path: string, symbol: string): string => `${path} declares ${symbol} already: nothing is written over code; write it by hand, or under another name`;

/** A judge of the agent's own appended to the harness file as code; the name the class imports it by. */
export function appendJudge(home: AgentHome, judge: JudgeWritten): Appended {
  const given: Record<string, unknown> = { name: judge.name, asks: judge.question };
  if (judge.answer !== "verdict") given["answer"] = judge.answer;
  if (judge.choices.length > 0) given["choices"] = judge.choices;
  if (judge.when !== "always") given["when"] = judge.when;
  if (judge.trigger !== "") given["trigger"] = judge.trigger;
  if (judge.reads.length > 0) given["reads"] = judge.reads;
  return append(home, "judge", judge.name, given);
}

/** A caller of the agent's own appended to the harness file as code; the name the class imports it by. */
export function appendPersona(home: AgentHome, persona: PersonaWritten): Appended {
  const given: Record<string, unknown> = { name: persona.name, goal: persona.goal, style: persona.style };
  if (persona.about !== undefined && persona.about !== "") given["about"] = persona.about;
  if (persona.facts !== undefined && Object.keys(persona.facts).length > 0) given["facts"] = persona.facts;
  if (persona.state !== undefined && Object.keys(persona.state).length > 0) given["state"] = persona.state;
  if (persona.expects !== undefined && persona.expects.length > 0) given["expects"] = persona.expects;
  if (persona.tags !== undefined && persona.tags.length > 0) given["tags"] = persona.tags;
  const behavior = Object.fromEntries(Object.entries(persona.behavior ?? {}).filter(([field, value]) => value !== BEHAVIOR_DEFAULTS[field]));
  if (Object.keys(behavior).length > 0) given["behavior"] = behavior;
  for (const field of ["llm", "tts", "voice"] as const) if (persona[field] !== undefined && persona[field] !== null) given[field] = persona[field];
  return append(home, "persona", persona.name, given);
}

function append(home: AgentHome, kind: "judge" | "persona", name: string, given: Record<string, unknown>): Appended {
  if (!A_NAME.test(name)) throw new UsageError(NOT_A_NAME(name));
  const language = languageOf(home.file);
  const symbol = symbolOf(language, name);
  const path = relative(home.root, home.harness);
  const before = existsSync(home.harness) ? readFileSync(home.harness, "utf8") : templateOf(language, home.name);
  if (new RegExp(`(^|[^A-Za-z0-9_])${symbol}\\s*=`, "m").test(before)) throw new UsageError(DECLARED_ALREADY(path, symbol));
  mkdirSync(dirname(home.harness), { recursive: true });
  const text = importing(language, before, language === "typescript" ? (kind === "judge" ? "ownJudge" : "ownPersona") : kind === "judge" ? "own_judge" : "own_persona");
  writeFileSync(home.harness, `${text.replace(/\n*$/, "\n")}\n${declaration(language, kind, symbol, given)}\n`, "utf8");
  return { path, symbol };
}

// A harness file that is not there is written as `pinecall new` writes it, from the same template, then appended to.
function templateOf(language: Language, slug: string): string {
  return readFileSync(join(TEMPLATE_ROOT, language, "agent", HARNESS_FILES[language]), "utf8").replaceAll("{{Title}}", titleOf(slug));
}

// A file that imports the package but not this constructor gets it on that line; Ruby's `Pinecall.` needs no import.
function importing(language: Language, text: string, ctor: string): string {
  if (language === "ruby") return text;
  const line = language === "typescript" ? new RegExp(`import \\{([^}]*)\\} from "${FRAMEWORK}";`) : /^from pinecall import (.+)$/m;
  const found = line.exec(text);
  const opening = language === "typescript" ? `import { ${ctor} } from "${FRAMEWORK}";` : `from pinecall import ${ctor}`;
  if (found === null) return `${opening}\n\n${text}`;
  const names = found[1]!.split(",").map((name) => name.trim()).filter((name) => name !== "");
  if (names.includes(ctor)) return text;
  const listed = [...names, ctor].sort().join(", ");
  return text.replace(found[0], language === "typescript" ? `import { ${listed} } from "${FRAMEWORK}";` : `from pinecall import ${listed}`);
}

// `offers-next-slot` is `offersNextSlot` to a TypeScript class, `OFFERS_NEXT_SLOT` to a Python or a Ruby one.
function symbolOf(language: Language, name: string): string {
  if (language === "typescript") return name.replace(/-([a-z0-9])/g, (_, letter: string) => letter.toUpperCase());
  return name.replaceAll("-", "_").toUpperCase();
}

function declaration(language: Language, kind: "judge" | "persona", symbol: string, given: Record<string, unknown>): string {
  if (language === "typescript") return `export const ${symbol} = ${kind === "judge" ? "ownJudge" : "ownPersona"}(${literal("typescript", camelKeys(given), "")});`;
  if (language === "python") return `${symbol} = ${kind === "judge" ? "own_judge" : "own_persona"}(\n${keywords("python", given)}\n)`;
  return `${symbol} = Pinecall.${kind === "judge" ? "own_judge" : "own_persona"}(\n${keywords("ruby", given)}\n)`;
}

// Python and Ruby take the fields as keywords, one per line: `name="…",` and `name: "…",` (Ruby's last with no comma).
function keywords(language: "python" | "ruby", given: Record<string, unknown>): string {
  const indent = language === "python" ? "    " : "  ";
  const lines = Object.entries(given).map(([key, value]) => `${indent}${key}${language === "python" ? "=" : ": "}${literal(language, value, indent)}`);
  return language === "python" ? lines.map((line) => `${line},`).join("\n") : lines.join(",\n");
}

/** A value as the language writes it: an object or a hash, a list, a string, a number, a boolean, nothing. */
export function literal(language: Language, value: unknown, indent: string): string {
  const inner = `${indent}  `;
  if (value === null || value === undefined) return language === "typescript" ? "null" : language === "python" ? "None" : "nil";
  if (typeof value === "boolean") return language === "python" ? (value ? "True" : "False") : String(value);
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return value.length === 0 ? "[]" : `[${value.map((one) => literal(language, one, indent)).join(", ")}]`;
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return "{}";
  const lines = entries.map(([key, one]) => `${inner}${keyOf(language, key)}${literal(language, one, inner)},`);
  return `{\n${lines.join("\n")}\n${indent}}`;
}

// A key as the language writes it in an object: bare or quoted in TypeScript, quoted in Python, a symbol in Ruby.
function keyOf(language: Language, key: string): string {
  if (language === "python") return `${JSON.stringify(key)}: `;
  if (language === "ruby") return /^[a-z_][a-z0-9_]*$/.test(key) ? `${key}: ` : `${JSON.stringify(key)} => `;
  return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(key) ? `${key}: ` : `${JSON.stringify(key)}: `;
}

// The TypeScript class reads the wire's keys camelCased: `pause_s` is `pauseS`; what a caller says (`facts`, `state`) is left as typed.
function camelKeys(given: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(given)) {
    const camel = key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
    out[camel] = key === "behavior" && typeof value === "object" && value !== null && !Array.isArray(value) ? camelKeys(value as Record<string, unknown>) : value;
  }
  return out;
}
