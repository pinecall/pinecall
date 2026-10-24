/** Runs one tool call: validates args, calls the method, trims the result to its preview. */

import { typesKnown } from "../agent/docstrings.js";
import type { ToolDeclaration } from "../agent/tools.js";

/** A tool failure with a message for the model. The SDK sends it as `tool.result.error`. */
export class ToolFailed extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ToolFailed";
  }
}

const ERASED = "its parameter types were erased when the file was compiled; hand the class its own source with describe(AgentClass, source)";

interface Parameters {
  properties?: Record<string, { type?: string | string[] }>;
  required?: string[];
}

// Schema property order is the signature's order (parametersOf writes it that way).
function orderOf(parameters: Parameters): string[] {
  return Object.keys(parameters.properties ?? {});
}

function typeOf(value: unknown): string {
  if (Array.isArray(value)) return "array";
  if (value === null) return "null";
  return typeof value;
}

// JSON Schema's `integer` is a number with no fraction, which `typeof` never says: `z.number().int()`
// refused every call (T F1, 2026-10-24). A list of types takes any of them.
function isA(value: unknown, wanted: string): boolean {
  if (wanted === "integer") return typeof value === "number" && Number.isInteger(value);
  return typeOf(value) === wanted;
}

function named(types: string[]): string {
  return types.map((type) => `${/^[aeiou]/.test(type) ? "an" : "a"} ${type}`).join(" or ");
}

// Checks only required names and top-level JSON types; nested shapes are the app's to validate.
function complaintsAbout(parameters: Parameters, args: Record<string, unknown>): string[] {
  const properties = parameters.properties ?? {};
  const complaints: string[] = [];
  for (const name of parameters.required ?? []) {
    if (args[name] === undefined) complaints.push(`${name} is required`);
  }
  for (const [name, schema] of Object.entries(properties)) {
    const value = args[name];
    if (value === undefined || schema.type === undefined) continue;
    const wanted = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!wanted.some((type) => isA(value, type))) {
      complaints.push(`${name} must be ${named(wanted)}, not ${wanted.includes("integer") && typeof value === "number" ? String(value) : named([typeOf(value)])}`);
    }
  }
  return complaints;
}

/** Validate args against the tool's schema. Returns complaints; empty means valid. */
export function validate(declaration: ToolDeclaration, args: Record<string, unknown>): string[] {
  return complaintsAbout(declaration.spec.parameters as Parameters, args ?? {});
}

/** Convert the model's args object into the method's positional arguments. */
export function argumentsFor(
  declaration: ToolDeclaration,
  args: Record<string, unknown>,
): unknown[] {
  return orderOf(declaration.spec.parameters as Parameters).map((name) => args?.[name]);
}

/** Trim an array result to the tool's `preview` row count; state still keeps the full result. */
export function preview(declaration: ToolDeclaration, result: unknown): unknown {
  const rows = declaration.options.preview;
  if (rows === undefined || !Array.isArray(result) || result.length <= rows) return result;
  return result.slice(0, rows);
}

/**
 * Run one tool call against a live agent. The method is called through the instance, not
 * `declaration.method`, because the decorator's wrapper authors writes with the tool's name.
 */
export async function runTool(
  agent: object,
  declaration: ToolDeclaration,
  args: Record<string, unknown>,
): Promise<unknown> {
  const complaints = validate(declaration, args);
  if (complaints.length > 0) {
    // Types the compiler erased read as objects, so the complaint would be about the schema, not the arguments.
    const cause = typesKnown(agent.constructor, declaration.name) ? complaints.join("; ") : ERASED;
    throw new ToolFailed(`${declaration.name}: ${cause}`);
  }
  const method = (agent as Record<string, unknown>)[declaration.name];
  if (typeof method !== "function") {
    throw new ToolFailed(`${declaration.name}: this agent has no such method any more`);
  }
  const result: unknown = await (method as (...rest: unknown[]) => unknown).apply(
    agent,
    argumentsFor(declaration, args),
  );
  return preview(declaration, result);
}
