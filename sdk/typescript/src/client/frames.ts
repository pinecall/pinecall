// Command frames, validated against their schema, and the client's error types.

import { type Camel, type CommandData, type EventData, toSnake } from "../wire/codec.js";
import { type Command, CommandSchema } from "../wire/envelope.js";
import { COMMAND_SCHEMAS, type CommandType } from "../wire/registry.js";

/** Base error for client-side and gateway refusals. */
export class PinecallError extends Error {
  override readonly name = "PinecallError";
}

/** A gateway refusal received as an `error` entry; match on `refusal.code`. */
export class Refused extends PinecallError {
  constructor(readonly refusal: Camel<EventData<"error">>) {
    super(`${refusal.code}: ${refusal.message}`);
  }
}

/**
 * Thrown by a dev verb handler to refuse with an HTTP status and a message shown verbatim. Any
 * other error becomes a 500.
 */
export class DevRefused extends PinecallError {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

let sent = 0;

/** Return a command id unique within this process; an `error` carrying it answers that command. */
export function nextId(): string {
  return `c${(sent += 1)}`;
}

/**
 * Build one command frame: camelCase data in, snake_case on the wire. Validates here so a bad
 * shape throws with the app's stack trace.
 */
export function frame<K extends CommandType>(
  type: K,
  agent: string,
  call: string | null,
  data: Camel<CommandData<K>>,
  id: string = nextId(),
): Command {
  // Typed structurally so this package never depends on a zod version.
  const schema = COMMAND_SCHEMAS[type] as { parse(value: unknown): unknown };
  let checked: unknown;
  try {
    checked = schema.parse(toSnake(data));
  } catch (bad) {
    throw new PinecallError(`${type}: ${bad instanceof Error ? bad.message : String(bad)}`);
  }
  return CommandSchema.parse({ type, agent, call, id, data: checked });
}
