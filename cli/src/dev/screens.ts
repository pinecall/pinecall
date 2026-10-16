/** `pinecall start` output modes: the plain log and the full-screen view, over the agent's process. */

import type { CamelEvent } from "@pinecall/agents/client";
import { toCamel } from "@pinecall/agents/wire";

import type { IO } from "../kit/io.js";
import { absorb, draw, screenFor, type Screen } from "./screen.js";
import type { EventLine, Serving } from "./serving.js";

// Repaint at most 10 times a second; per-event redraws flicker.
const FRAME_MS = 100;

const CLEAR = "\x1b[2J\x1b[3J\x1b[H";
const KEYS = "keys: p pause · c clear · e events · q quit";

/** Subscribe to an agent's events; returns an unsubscribe function. */
export type Listen = (listener: (event: CamelEvent) => void) => () => void;

/** The agent's process, as the screens see it: its lines, and when it is gone. */
export interface Running {
  /** Resolves with its exit code. */
  gone: Promise<number>;
  /** Ask it to leave, as a signal would. */
  leave(): Promise<number>;
}

/** One agent in the plain log: its events, its `connected` line, and lines printed after it. */
export interface PlainAgent {
  slug: string;
  heard: Listen;
  connected: string;
  after: () => Promise<string[]>;
}

/** One agent's entries off the process's lines, as the screens read them. */
export function listenTo(serving: Serving, slug: string): Listen {
  return (listener: (event: CamelEvent) => void) =>
    serving.onEvent((line: EventLine) => {
      if (line.agent === slug) listener({ type: line.type, data: toCamel(line.data) } as CamelEvent);
    });
}

// Default mode: append-only lines without cursor movement, for process managers and `docker logs`.
// With several agents each line is prefixed with the slug. Ends when the agent's process does.
export async function plain(io: IO, running: Running, agents: PlainAgent[], url: string): Promise<number> {
  const width = Math.max(...agents.map((agent) => agent.slug.length));
  const prefix = (slug: string): string => (agents.length > 1 ? `${slug.padEnd(width)} │ ` : "");
  for (const agent of agents) {
    let screen = screenFor(agent.slug, url);
    agent.heard((event) => {
      const before = screen;
      screen = absorb(screen, event);
      for (const line of newLines(before, screen)) io.print(`${prefix(agent.slug)}${line}`);
    });
  }
  for (const agent of agents) io.print(`${prefix(agent.slug)}${agent.connected}`);
  for (const agent of agents) {
    for (const said of await agent.after()) io.print(`${prefix(agent.slug)}${said}`);
  }
  return await running.gone;
}

// Lines an event added to the screen, so the plain log appends only those.
function newLines(before: Screen, after: Screen): string[] {
  const lines: string[] = [];
  for (const line of after.transcript.slice(before.transcript.length)) lines.push(`${line.mark} ${line.text}`);
  for (const line of after.tools.slice(before.tools.length)) lines.push(`${line.mark} ${line.text}`);
  for (const metric of after.metrics.slice(before.metrics.length)) lines.push(`metrics  ${metric}`);
  if (after.changed !== before.changed && after.changed.length > 0) {
    lines.push(`state    ${after.changed.join(", ")}`);
  }
  return lines;
}

/** The agent the full-screen view shows. */
export interface Watching {
  slug: string;
  url: string;
}

/** The full-screen terminal view, repainted at most ten times a second, until `q` or the process leaves. */
export async function live(io: IO, running: Running, listen: Listen, watching: Watching, input: NodeJS.ReadStream = process.stdin): Promise<number> {
  let screen = screenFor(watching.slug, watching.url);
  let paused = false;
  let raw = false;
  let dirty = true;
  const terminal = io.stdout as NodeJS.WriteStream;

  const paint = (): void => {
    if (paused || !dirty) return;
    dirty = false;
    const rows = terminal.rows ?? 40;
    const columns = terminal.columns ?? 100;
    const page = draw(screen, rows - 3, columns, raw);
    io.stdout.write(`${CLEAR}${page}\n\n${KEYS}\n`);
  };

  listen((event) => {
    screen = absorb(screen, event);
    dirty = true;
  });

  const timer = setInterval(paint, FRAME_MS);
  paint();
  // Raw mode turns ^C into a key, so it asks the process to leave as q does; SIGTERM still arrives
  // as a signal, and the process leaves on its own.
  const quit = await new Promise<boolean>((done) => {
    const stop = onKey(input, (key) => {
      if (key === "q" || key === "\u0003") {
        stop();
        done(true);
        return;
      }
      if (key === "p") paused = !paused;
      if (key === "c") screen = screenFor(watching.slug, watching.url);
      if (key === "e") raw = !raw;
      dirty = true;
    });
    void running.gone.finally(() => {
      stop();
      done(false);
    });
  });
  clearInterval(timer);
  io.stdout.write(CLEAR);
  return quit ? await running.leave() : await running.gone;
}

// Raw mode for single keypresses; without a TTY there are no keys but the view still draws.
function onKey(input: NodeJS.ReadStream, handle: (key: string) => void): () => void {
  if (!input.isTTY) return () => undefined;
  input.setRawMode(true);
  input.resume();
  input.setEncoding("utf8");
  const listener = (chunk: string): void => handle(chunk);
  input.on("data", listener);
  return () => {
    input.off("data", listener);
    input.setRawMode(false);
    input.pause();
  };
}
