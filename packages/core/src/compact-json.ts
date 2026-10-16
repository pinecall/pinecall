/** Format payloads as Python's compact JSON, matching `pinecall-runtime sessions show`. */

import { isEventType } from "./wire/codec.js";
import { EVENT_SCHEMAS } from "./wire/registry.js";
import { z } from "zod";

/** The subset of JSON Schema this file reads. */
export interface Shape {
  type?: string;
  properties?: Record<string, Shape>;
  items?: Shape;
  oneOf?: Shape[];
  const?: unknown;
}

/** JSON Schema for each named event type. */
export function shapesFor(types: Iterable<string>): Map<string, Shape> {
  const shapes = new Map<string, Shape>();
  for (const type of types) {
    if (!shapes.has(type) && isEventType(type)) {
      shapes.set(type, z.toJSONSchema(EVENT_SCHEMAS[type], { io: "input" }) as Shape);
    }
  }
  return shapes;
}

/** Serialize like Python's `json.dumps(separators=(",", ":"), ensure_ascii=False)`. */
export function compact(value: unknown, shape?: Shape): string {
  if (value === null || value === undefined) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    return asPython(value, shape);
  }
  if (Array.isArray(value)) {
    return `[${value.map((one) => compact(one, shape?.items)).join(",")}]`;
  }
  return braced(value as Record<string, unknown>, shape);
}

/** Strings verbatim, everything else via `compact`. */
export function said(value: unknown, shape?: Shape): string {
  return typeof value === "string" ? value : compact(value, shape);
}

function braced(value: Record<string, unknown>, shape?: Shape): string {
  const declared = branch(value, shape)?.properties;
  const pairs = Object.entries(value).map(
    ([name, held]) => `${JSON.stringify(name)}:${compact(held, declared?.[name])}`,
  );
  return `{${pairs.join(",")}}`;
}

// Pick the oneOf branch whose `const` fields match the value (discriminated unions).
function branch(value: Record<string, unknown>, shape?: Shape): Shape | undefined {
  if (shape?.oneOf === undefined) {
    return shape;
  }
  return shape.oneOf.find((option) =>
    Object.entries(option.properties ?? {}).every(
      ([name, field]) => field.const === undefined || field.const === value[name],
    ),
  );
}

// JSON loses int vs float, so the schema decides: declared floats get Python's repr (`0.0`,
// exponent below 1e-4 or from 1e16).
function asPython(value: number, shape?: Shape): string {
  if (shape?.type !== "number" || !Number.isFinite(value)) {
    return String(value);
  }
  const magnitude = Math.abs(value);
  if (value !== 0 && (magnitude < 1e-4 || magnitude >= 1e16)) {
    return exponential(value);
  }
  return Number.isInteger(value) ? `${value}.0` : String(value);
}

// Python pads the exponent to two digits with a sign: 1e-06, not 1e-6.
function exponential(value: number): string {
  const [mantissa = "", exponent = ""] = value.toExponential().split("e");
  const sign = exponent.startsWith("-") ? "-" : "+";
  return `${mantissa}e${sign}${exponent.replace(/^[+-]/, "").padStart(2, "0")}`;
}
