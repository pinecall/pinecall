/** The tool registry: declared tools, their wire specs, and which are visible in the current state. */

import { z } from "zod";
import { type ToolSpec } from "../wire/defs.js";
import { classDoc, docsVersion, methodDoc, methodParams, type ParamDoc } from "./docstrings.js";
import type { StageOf } from "./stages.js";
import { snapshot, type Snapshot } from "./state.js";

// Generated wire type (snake_case fields).
export type { ToolSpec };

// `read`, `write` (undoable) or `irreversible` (the platform asks the caller first).
export type SideEffect = NonNullable<ToolSpec["side_effect"]>;

/** Options for `@tool({...})`. `T` is inferred from the decorated class, so `when` sees typed state. */
export interface ToolOptions<T = unknown> {
  /** Show the tool only while this returns true for the current state. */
  when?: (state: Snapshot<T>) => boolean;
  /**
   * Show the tool only in these stages, typed against the class's `stage` field. Combined with
   * `when`, both must hold.
   */
  stage?: StageOf<T> | StageOf<T>[];
  /** Confirmation read back after the tool runs; `{{result.x}}` is filled from its return value. Marks the tool irreversible. */
  confirm?: string;
  /** What the agent says as the tool starts ("Let me check the agenda."), when the model's turn said nothing itself. */
  announce?: string;
  /** Number of rows of a list result shown to the model; the full result is kept. */
  preview?: number;
  /** Parameter names holding personal data, masked in the log. */
  pii?: string[];
  /** Timeout for the method, in seconds. */
  timeout?: number;
  /** Explicit parameter schema, overriding the one inferred from the signature. */
  params?: z.ZodObject;
}

// The registry spans all classes, so the class type of `when` is erased.
export type ErasedToolOptions = ToolOptions<any>;

/** A declared tool: its options, method, owning class and wire spec. */
export interface ToolDeclaration {
  name: string;
  options: ErasedToolOptions;
  method: (...args: unknown[]) => unknown;
  owner: Function;
  spec: ToolSpec;
}

/** Thrown at declaration time for a tool or class the platform would refuse. */
export class DeclarationRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DeclarationRefused";
  }
}

interface Declared {
  name: string;
  options: ErasedToolOptions;
  method: (...args: unknown[]) => unknown;
}

// Keyed by prototype; subclasses inherit by walking the chain at read time.
const registries = new WeakMap<object, Map<string, Declared>>();
const specs = new WeakMap<object, Map<string, { spec: ToolSpec; version: number }>>();

const A_NAME_A_MODEL_CAN_CALL = /^[A-Za-z][A-Za-z0-9_]*$/;

/** Record one decorated method against the class that declared it. */
export function register(prototype: object, declared: Declared): void {
  if (!A_NAME_A_MODEL_CAN_CALL.test(declared.name)) {
    throw new DeclarationRefused(`a tool name is one word a model can call, not ${declared.name}`);
  }
  let registry = registries.get(prototype);
  if (!registry) {
    registry = new Map();
    registries.set(prototype, registry);
  }
  registry.set(declared.name, declared);
}

// Fallback for bare type text when `param.schema` is absent; unknown shapes become open objects.
function schemaOf(type: string | undefined): Record<string, unknown> {
  const name = (type ?? "").split(" ").join("");
  if (name.includes("=>")) return { description: "callback" };
  if (name.endsWith("[]")) return { type: "array", items: schemaOf(name.slice(0, -2)) };
  if (name === "string" || name === "number" || name === "boolean") return { type: name };
  return { type: "object", additionalProperties: true };
}

/** JSON Schema for a tool's parameters, from an explicit zod object or from the signature. */
export function parametersOf(params: ParamDoc[], explicit?: z.ZodObject): Record<string, unknown> {
  if (explicit) return z.toJSONSchema(explicit) as Record<string, unknown>;
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  for (const param of params) {
    const schema = param.schema ?? schemaOf(param.type);
    properties[param.name] = schema;
    // The model cannot supply a callback, so it is never required.
    if (!param.optional && schema["description"] !== "callback") required.push(param.name);
  }
  return { type: "object", properties, required, additionalProperties: false };
}

/** Build the wire spec for one declared tool, refusing what the gateway would refuse. */
function specFor(ctor: Function, declared: Declared): ToolSpec {
  const description = methodDoc(ctor, declared.name);
  if (!description) {
    throw new DeclarationRefused(
      `tool ${declared.name}: without a docstring no model can choose it; ` +
        `write a /** one line */ above the method`,
    );
  }
  const options = declared.options;
  const parameters = parametersOf(methodParams(ctor, declared.name), options.params);
  const properties = (parameters["properties"] ?? {}) as Record<string, unknown>;
  const unknownPii = (options.pii ?? []).filter((field) => !(field in properties));
  if (unknownPii.length > 0) {
    throw new DeclarationRefused(
      `tool ${declared.name}: pii names parameters the tool has; unknown: ${unknownPii.join(", ")}`,
    );
  }
  // `confirm` makes a tool irreversible: the platform reads it back and waits for a yes.
  const spec: ToolSpec = {
    name: declared.name,
    description,
    parameters,
    side_effect: options.confirm ? "irreversible" : "read",
  };
  if (options.confirm !== undefined) spec.confirm = options.confirm;
  if (options.announce !== undefined) spec.announce = options.announce;
  if (options.pii !== undefined) spec.pii = [...options.pii];
  if (options.timeout !== undefined) spec.timeout_s = options.timeout;
  return spec;
}

function cachedSpec(ctor: Function, prototype: object, declared: Declared): ToolSpec {
  let byName = specs.get(prototype);
  if (!byName) {
    byName = new Map();
    specs.set(prototype, byName);
  }
  const known = byName.get(declared.name);
  if (known && known.version === docsVersion()) return known.spec;
  const spec = specFor(ctor, declared);
  byName.set(declared.name, { spec, version: docsVersion() });
  return spec;
}

// Without a `stage` field every staged tool would stay hidden. The compiler catches this in TS;
// this catches it for JavaScript classes, at mount.
function refuseAStageWithNoField(agent: object, ctor: Function, name: string): void {
  if ("stage" in agent) return;
  throw new DeclarationRefused(
    `tool ${name}: stage names a value of this agent's own stage field, and ${ctor.name} ` +
      `declares none; add \`stage: Stages<"…"> = "…"\` to the class, or ask when(state) instead`,
  );
}

/** Every tool the agent declares, own class first, then inherited. */
export function toolsOf(agent: object): ToolDeclaration[] {
  const ctor = (agent as { constructor: Function }).constructor;
  const declarations: ToolDeclaration[] = [];
  const seen = new Set<string>();
  for (
    let prototype: object | null = Object.getPrototypeOf(agent);
    prototype && prototype !== Object.prototype;
    prototype = Object.getPrototypeOf(prototype)
  ) {
    for (const declared of registries.get(prototype)?.values() ?? []) {
      if (seen.has(declared.name)) continue;
      seen.add(declared.name);
      if (declared.options.stage !== undefined) refuseAStageWithNoField(agent, ctor, declared.name);
      declarations.push({
        name: declared.name,
        options: declared.options,
        method: declared.method,
        owner: (prototype as { constructor: Function }).constructor,
        spec: cachedSpec(ctor, prototype, declared),
      });
    }
  }
  return declarations;
}

/** A declared tool by name. */
export function toolNamed(agent: object, name: string): ToolDeclaration | undefined {
  return toolsOf(agent).find((declared) => declared.name === name);
}

/** Tools whose `when` holds for the current state. */
export function visibleToolsOf(agent: object): ToolDeclaration[] {
  const state = snapshot(agent);
  return toolsOf(agent).filter((declared) => declared.options.when?.(state) ?? true);
}

/** Wire specs of the currently visible tools. */
export function visibleTools(agent: object): ToolSpec[] {
  return visibleToolsOf(agent).map((declared) => declared.spec);
}

/** The agent class's docstring. */

export function docOf(agent: object): string | undefined {
  return classDoc((agent as { constructor: Function }).constructor);
}
