/** Lifecycle hooks: call start, call end, memory writes and external events. */

import { type Medium } from "../wire/defs.js";

import { withAuthorAsync } from "./authors.js";
import type { EventMeta } from "./accepts.js";

/** The call passed to lifecycle hooks. */
export interface Call {
  id: string;
  contact: string;
  from?: string;
  channel?: string;
  /** Spoken or written, when the gateway says. */
  medium?: Medium;
}

/** A memory write: remember or forget a key about the contact. */
export interface MemoryOp {
  op: "remember" | "forget";
  key: string;
  value?: unknown;
}

/** Hooks an agent may override; all default to no-ops. */
export interface Lifecycle {
  onCall(call: Call): unknown;
  onEnd(call: Call): unknown;
  onMemory(ops: MemoryOp[], call: Call): unknown;
  onEvent(name: string, data: Record<string, unknown>, meta: EventMeta): unknown;
}

export type HookName = keyof Lifecycle;

/** Run a hook with its state writes authored as `hook:<name>`; hooks and tools are the only writers. */

export function runHook<K extends HookName>(
  agent: Lifecycle,
  hook: K,
  ...args: Parameters<Lifecycle[K]>
): Promise<unknown> {
  const method = agent[hook] as (...rest: unknown[]) => unknown;
  return withAuthorAsync(`hook:${hook}`, () => method.apply(agent, args));
}
