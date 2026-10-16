/** What a serve entry says on its `--events` stdout: one wire entry a line, read into apps and events. */

import { createInterface } from "node:readline";
import type { Readable, Writable } from "node:stream";

import { UsageError } from "../errors.js";

/** One line the serve entry printed: the entry as the gateway wrote it, in snake_case. */
export interface EventLine {
  type: string;
  agent: string;
  call: string | null;
  data: Record<string, unknown>;
}

/** The agents a serve entry holds, as its lines tell them. */
export interface Serving {
  /** The app id the agent was last registered under, or undefined before it was. */
  app(slug: string): string | undefined;
  /** Resolves with the app id on the agent's first registration; refused when none comes in time. */
  registered(slug: string): Promise<string>;
  /** Every entry line from now on. The returned function stops listening. */
  onEvent(listener: (line: EventLine) => void): () => void;
}

/** An agent some process serves: its slug, and that process's app id, read anew on every dial. */
export interface Served {
  slug: string;
  app(): string | undefined;
}

/** The agent as the gateway serves it: no app named, so a call goes to the newest that holds the slug in the env. */
export function servedByTheGateway(slug: string): Served {
  return { slug, app: () => undefined };
}

/** Long enough for tsx to compile a class and a socket to register it on a slow machine. */
const REGISTERS_WITHIN_MS = 30_000;

/**
 * Read a serve entry's lines. A line that is no JSON entry is passed to `other` as it came; a later
 * registration of a slug (a gateway restart) replaces its app id.
 */
export function servingFrom(lines: Readable, other: Writable, withinMs = REGISTERS_WITHIN_MS): Serving {
  const apps = new Map<string, string>();
  const listeners = new Set<(line: EventLine) => void>();
  const waiting = new Map<string, ((app: string) => void)[]>();
  createInterface({ input: lines }).on("line", (text) => {
    const line = eventLineOf(text);
    if (line === undefined) return void other.write(`${text}\n`);
    if (line.type === "agent.registered" && typeof line.data["app"] === "string") {
      apps.set(line.agent, line.data["app"]);
      for (const answer of waiting.get(line.agent) ?? []) answer(line.data["app"]);
      waiting.delete(line.agent);
    }
    for (const listener of listeners) listener(line);
  });
  return {
    app: (slug) => apps.get(slug),
    registered: (slug) => {
      const known = apps.get(slug);
      if (known !== undefined) return Promise.resolve(known);
      return new Promise((answer, refuse) => {
        const late = setTimeout(() => refuse(new UsageError(`${slug} did not register within ${withinMs / 1000}s`)), withinMs);
        late.unref();
        waiting.set(slug, [...(waiting.get(slug) ?? []), (app) => (clearTimeout(late), answer(app))]);
      });
    },
    onEvent: (listener) => {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
  };
}

function eventLineOf(text: string): EventLine | undefined {
  try {
    const parsed = JSON.parse(text) as Partial<EventLine>;
    if (typeof parsed.type !== "string" || typeof parsed.agent !== "string") return undefined;
    return { type: parsed.type, agent: parsed.agent, call: parsed.call ?? null, data: parsed.data ?? {} };
  } catch {
    return undefined;
  }
}
