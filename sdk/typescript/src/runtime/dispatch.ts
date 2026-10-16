/** Dispatches `event.received` entries to the instance serving the call, or drops them. */

import { emitEvent, type EventHeard } from "../agent/agent.js";
import { withAuthorAsync } from "../agent/authors.js";
import { accepts, type EventMeta, type EventSource } from "../agent/accepts.js";
import type { CallWorld } from "../call/call.js";

/** One `event.received` entry as the wire carries it. */
export interface Received {
  name: string;
  data: Record<string, unknown>;
  source: EventSource;
  identity?: string;
  seq: number;
}

/** The live instance, its class and its call, as the dispatcher needs them. */
export interface Serving {
  agent: object;
  ctor: Function;
  call: CallWorld;
  /** `call:name` keys already warned about, so each warns once. */
  warned: Set<string>;
  /** Serializes this call's events so a write's cause is the event currently running. */
  queue: Promise<unknown>;
}

/**
 * Dispatch after all earlier events finish. The cause lives on the call while a hook runs, so
 * concurrent hooks would attribute writes to each other's event.
 */
export function inOrder(serving: Serving, received: Received): Promise<boolean> {
  const next = serving.queue.then(() => dispatch(serving, received));
  // A throwing hook must not block later events; the rejection goes to the caller.
  serving.queue = next.catch(() => undefined);
  return next;
}

/**
 * Pass the event to `onEvent` if its name and source are declared, else drop it. Writes inside the
 * hook are authored `event:<name>`, and the call carries the cause so the log can name it.
 */
export async function dispatch(serving: Serving, received: Received): Promise<boolean> {
  const { name, data, source, seq } = received;
  if (!accepts(serving.ctor, name, source)) {
    warn(serving, name, source);
    return false;
  }
  const meta: EventMeta = { source, seq, ...(received.identity === undefined ? {} : { identity: received.identity }) };
  const hook = (serving.agent as { onEvent: (n: string, d: Record<string, unknown>, m: EventMeta) => unknown }).onEvent;
  serving.call.cause = { name, seq };
  try {
    await withAuthorAsync(`event:${name}`, () => hook.call(serving.agent, name, data, meta));
  } finally {
    serving.call.cause = null;
  }
  const heard: EventHeard = { name, data, meta };
  emitEvent(serving.agent, heard);
  return true;
}

// Once per (call, name): a backend sending an undeclared event usually sends it repeatedly.
function warn(serving: Serving, name: string, source: EventSource): void {
  const key = `${serving.call.id}:${name}`;
  if (serving.warned.has(key)) return;
  serving.warned.add(key);
  console.warn(`pinecall: event ${name} from ${source} is not declared by this agent; dropped`);
}
