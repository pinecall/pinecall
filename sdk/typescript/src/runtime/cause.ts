/** The cause a `state.set` names for a write: the tool, the event handler or the hook that made it. */

import { currentToolCall, hookOf, isEvent } from "../agent/authors.js";
import type { CallWorld } from "../call/call.js";
import type { Camel } from "../wire/codec.js";
import type { StateCause } from "../wire/defs.js";

// The hooks whose writes the wire names; `onEnd` writes after the call is over, and none is sent.
const HOOKS: Record<string, "on_call" | "on_memory"> = { onCall: "on_call", onMemory: "on_memory" };

/**
 * What to say of a write by its author, read where it is made: the tool call id is on the async
 * context, and the event being handled is on the call. A writer the wire has no kind for says nothing.
 */
export function causeOf(author: string, world: CallWorld): Camel<StateCause> | undefined {
  const named = hookOf(author);
  if (named !== null) {
    const hook = HOOKS[named];
    return hook === undefined ? undefined : { kind: "hook", hook };
  }
  if (isEvent(author)) {
    return world.cause === null ? undefined : { kind: "event", name: world.cause.name, seq: world.cause.seq };
  }
  const id = currentToolCall();
  return id === null ? undefined : { kind: "tool", tool: author, callId: id };
}
