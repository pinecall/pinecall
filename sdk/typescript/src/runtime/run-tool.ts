/** Runs one tool call: validates args, calls the method, trims the result to its preview. */

import type { ToolDeclaration } from "../agent/tools.js";

/** A tool failure with a message for the model. The SDK sends it as `tool.result.error`. */
export class ToolFailed extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ToolFailed";
  }
}

interface Parameters {
  properties?: Record<string, { type?: string }>;
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

// Checks only required names and top-level JSON types; nested shapes are the app's to validate.
function complaintsAbout(parameters: Parameters, args: Record<string, unknown>): string[] {
  const properties = parameters.properties ?? {};
  const complaints: string[] = [];
  for (const name of parameters.required ?? []) {
    if (args[name] === undefined) complaints.push(`${name} is required`);
  }
  for (const [name, schema] of Object.entries(properties)) {
    const value = args[name];
    const wanted = schema.type;
    if (value === undefined || wanted === undefined) continue;
    if (typeOf(value) !== wanted) {
      complaints.push(`${name} must be a ${wanted}, not a ${typeOf(value)}`);
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
    throw new ToolFailed(`${declaration.name}: ${complaints.join("; ")}`);
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
