/** What a served process prints of its agent's entries: the values the agent declared private, masked as the call's log masks them. */

import type { AgentOptions } from "../client/index.js";
import type { Entry } from "../wire/envelope.js";

const MASK = "***";

// A value shorter than this is never learned: "7", "ok" or "Al" cannot be told from a word, and masking
// it would mask every such digit or word printed after it. The argument is still masked by its name.
const LEAST_SECRET_CHARS = 3;

// What the agent wrote down, by entry: the fields of its data a private value may be in. What was
// said is the caller's and the model's words, and never masked.
const WRITTEN_DOWN: Record<string, string[]> = {
  "tool.call": ["arguments"],
  "tool.result": ["output", "error", "summary"],
  "state.changed": ["state"],
  "call.attached": ["state"],
  custom: ["data"],
};

type Data = Record<string, unknown>;

/** One agent's private names and, as its tool calls pass, the private values they carried. */
export class Masking {
  readonly #values = new Set<string>();
  readonly #arguments = new Map<string, Set<string>>();
  readonly #fields = new Set<string>();

  constructor(declared: Pick<AgentOptions, "tools" | "stateFields">) {
    for (const tool of declared.tools ?? []) this.#arguments.set(tool.name, new Set(tool.pii ?? []));
    for (const field of declared.stateFields ?? []) if (field.visibility === "pii") this.#fields.add(field.name);
  }

  /** The entry with every private value masked: by name where the agent named it, by value wherever else it was written down. */
  entry(entry: Entry): Entry {
    const fields = WRITTEN_DOWN[entry.type];
    if (fields === undefined || (this.#values.size === 0 && this.#fields.size === 0 && !this.#carries(entry))) return entry;
    if (entry.type === "tool.call") this.#learn(entry.data);
    const secrets = secretsOf(this.#values);
    const data: Data = { ...entry.data };
    for (const field of fields) {
      if (field in data) data[field] = masked(data[field], this.#namesIn(entry, field), secrets);
    }
    return { ...entry, data };
  }

  #carries(entry: Entry): boolean {
    return entry.type === "tool.call" && (this.#arguments.get(String(entry.data["name"]))?.size ?? 0) > 0;
  }

  #namesIn(entry: Entry, field: string): ReadonlySet<string> {
    if (entry.type === "tool.call" && field === "arguments") return this.#arguments.get(String(entry.data["name"])) ?? new Set();
    return field === "state" ? this.#fields : new Set();
  }

  #learn(data: Data): void {
    const given = data["arguments"] as Data | undefined;
    for (const name of this.#arguments.get(String(data["name"])) ?? []) {
      for (const leaf of leaves(given?.[name])) if (leaf.length >= LEAST_SECRET_CHARS) this.#values.add(leaf);
    }
  }
}

// A field of members is masked member by member; any other value is masked of the secrets alone.
function masked(value: unknown, names: ReadonlySet<string>, secrets: Secrets): unknown {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return scrubbed(value, secrets);
  return Object.fromEntries(
    Object.entries(value).map(([name, member]) => [name, names.has(name) ? MASK : scrubbed(member, secrets)]),
  );
}

interface Secrets {
  pattern: RegExp | null;
  whole: ReadonlySet<string>;
}

// A value is a secret where it stands as a whole word: `Ana` is no part of `Banana` or `Anabel`. The
// longest alternative comes first, so a value that holds another is masked whole.
function secretsOf(values: ReadonlySet<string>): Secrets {
  if (values.size === 0) return { pattern: null, whole: values };
  const words = [...values].sort((a, b) => b.length - a.length).map((value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return { pattern: new RegExp(`(?<![\\p{L}\\p{N}_])(?:${words.join("|")})(?![\\p{L}\\p{N}_])`, "gu"), whole: values };
}

// A leaf that is a private value goes whole; a string that holds one as a word has it replaced.
function scrubbed(value: unknown, secrets: Secrets): unknown {
  if (secrets.pattern === null) return value;
  if (typeof value === "string") return value.replace(secrets.pattern, MASK);
  if (typeof value === "number") return secrets.whole.has(String(value)) ? MASK : value;
  if (Array.isArray(value)) return value.map((item) => scrubbed(item, secrets));
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(Object.entries(value).map(([name, member]) => [name, scrubbed(member, secrets)]));
  }
  return value;
}

// Every string and number inside a value, as text; a blank is no secret, it would mask everything.
function leaves(value: unknown): string[] {
  if (typeof value === "string") return value.trim() === "" ? [] : [value.trim()];
  if (typeof value === "number") return [String(value)];
  if (Array.isArray(value)) return value.flatMap(leaves);
  if (typeof value === "object" && value !== null) return Object.values(value).flatMap(leaves);
  return [];
}
