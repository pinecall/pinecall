/** A call as a hook and as the class read it: the line's facts off the client's call, and a logged value as an object. */

import type { Call as SdkCall } from "../client/index.js";

import type { Call as HookCall } from "../agent/lifecycle.js";
import type { CallLine } from "../call/call.js";

/** The call a hook is handed: who is on it and what it came in on. */
export function hookCall(call: SdkCall): HookCall {
  const hook: HookCall = { id: call.id, contact: call.contact?.id ?? call.from ?? "" };
  if (call.from !== null) hook.from = call.from;
  if (call.channel !== null) hook.channel = call.channel;
  if (call.medium !== null) hook.medium = call.medium;
  return hook;
}

// Adds what hookCall lacks: without it `this.call.today` or `this.call.to` is undefined.
export function callLine(call: SdkCall): CallLine {
  const line: CallLine = { ...hookCall(call), today: call.today, claimed: call.claimed, metadata: call.metadata };
  if (call.to !== null) line.to = call.to;
  if (call.direction !== null) line.direction = call.direction;
  if (call.contact !== null) line.caller = call.contact;
  return line;
}

// call.log requires an object, so wrap other values under `value`.
export function dataOf(data: unknown): Record<string, unknown> {
  if (data === undefined) return {};
  if (typeof data === "object" && data !== null && !Array.isArray(data)) {
    return data as Record<string, unknown>;
  }
  return { value: data };
}
