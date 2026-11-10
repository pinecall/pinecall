/** What a Studio tool may be: the names refused, a new one, and its parameters as JSON Schema and back. */

import type { FixedField, HttpTool, Param } from "./door";

export const METHODS: readonly HttpTool["method"][] = ["GET", "POST", "PUT", "PATCH", "DELETE"];
export const PARAM_TYPES: readonly Param["type"][] = ["string", "number", "integer", "boolean"];
// runtime studio/service/definition.py: the platform's own tools, which a Studio tool may not be called.
const THE_PLATFORMS = ["collect", "end_call", "current_date", "recall", "search", "say"];
const A_NAME = /^[A-Za-z][A-Za-z0-9_]*$/;
export const LONGEST_S = 30;
export const DELAYED_AFTER_S = 5;

export function aTool(taken: readonly HttpTool[]): HttpTool {
  let at = taken.length + 1;
  while (taken.some((tool) => tool.name === `tool_${at}`)) at += 1;
  return { name: `tool_${at}`, description: "", method: "GET", url: "https://", headers: [], params: [], fixed: [], announce: null, delayed: null, delayed_after_s: DELAYED_AFTER_S, failed: null, timeout_s: 10 };
}

export const aParam = (): Param => ({ name: "", type: "string", description: "", required: true, enum: null });

export function nameRefused(name: string, others: readonly HttpTool[]): string | null {
  if (!A_NAME.test(name)) return "Starts with a letter, then letters, digits or _.";
  if (THE_PLATFORMS.includes(name)) return `${name} is one of the platform's own tools.`;
  return others.some((one) => one.name === name) ? "Another tool has this name." : null;
}

/** What is wrong with a tool before the gateway sees it, or nothing: the same sentences the gateway would say, said first. */
export function toolRefused(tool: HttpTool, others: readonly HttpTool[]): string | null {
  const name = nameRefused(tool.name, others);
  if (name !== null) return name;
  const params = new Set<string>();
  for (const param of tool.params) {
    if (!A_NAME.test(param.name)) return `Parameter "${param.name}": starts with a letter, then letters, digits or _.`;
    if (params.has(param.name)) return `Two parameters are called ${param.name}.`;
    params.add(param.name);
    if (param.enum !== null && param.enum !== undefined && param.type !== "string") return `${param.name} lists its values, which a ${param.type} cannot: a closed list is a string's.`;
  }
  const fixed = new Set<string>();
  for (const field of tool.fixed) {
    if (!A_NAME.test(field.name)) return `Static field "${field.name}": starts with a letter, then letters, digits or _.`;
    if (fixed.has(field.name)) return `Two static fields are called ${field.name}.`;
    if (params.has(field.name)) return `${field.name} is both a parameter the model fills and a static field: one or the other.`;
    fixed.add(field.name);
  }
  return null;
}

export function hostOf(url: string): string {
  return url.replace(/^https?:\/\//, "") || "No URL yet";
}

export function replaced<T>(list: readonly T[], at: number, item: T): T[] {
  return list.map((one, index) => (index === at ? item : one));
}

export function without<T>(list: readonly T[], at: number): T[] {
  return list.filter((_, index) => index !== at);
}

// ── the parameters as JSON Schema, the way the model is told them ──

interface Property {
  type: Param["type"];
  description?: string;
  enum?: string[];
}

export interface ParamsSchema {
  type: "object";
  properties: Record<string, Property>;
  required: string[];
  additionalProperties: false;
}

/** The params as the JSON tab shows them: the object schema the model is given, every extra property refused. */
export function schemaOf(params: readonly Param[]): ParamsSchema {
  const properties: Record<string, Property> = {};
  for (const param of params) {
    properties[param.name] = {
      type: param.type,
      ...(param.description !== "" ? { description: param.description } : {}),
      ...(param.enum !== null && param.enum !== undefined && param.enum.length > 0 ? { enum: param.enum } : {}),
    };
  }
  return { type: "object", properties, required: params.filter((param) => param.required).map((param) => param.name), additionalProperties: false };
}

const NOT_A_SCHEMA = "The JSON is an object schema: {\"type\": \"object\", \"properties\": {…}, \"required\": […]}.";

/** The params read back from the JSON tab, or why they cannot be: a flat object of strings, numbers and booleans. */
export function paramsOf(text: string): { params: Param[] } | { refused: string } {
  let read: unknown;
  try {
    read = JSON.parse(text);
  } catch (failed) {
    return { refused: failed instanceof Error ? failed.message : "Not JSON." };
  }
  if (!isRecord(read) || read.type !== "object" || !isRecord(read.properties)) return { refused: NOT_A_SCHEMA };
  const required = Array.isArray(read.required) ? read.required.filter((one): one is string => typeof one === "string") : [];
  const params: Param[] = [];
  for (const [name, property] of Object.entries(read.properties)) {
    if (!isRecord(property)) return { refused: `${name}: a property is an object with a type.` };
    const type = property.type;
    if (typeof type !== "string" || !PARAM_TYPES.includes(type as Param["type"])) return { refused: `${name}: the type is string, number, integer or boolean; objects and arrays are not taken.` };
    const values = property.enum;
    if (values !== undefined && (!Array.isArray(values) || values.some((one) => typeof one !== "string"))) return { refused: `${name}: enum is a list of strings.` };
    params.push({
      name,
      type: type as Param["type"],
      description: typeof property.description === "string" ? property.description : "",
      required: required.includes(name),
      enum: Array.isArray(values) && values.length > 0 ? (values as string[]) : null,
    });
  }
  return { params };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// ── authorization, as a header the request carries ──

export type AuthScheme = "none" | "bearer" | "header";

/** What the headers say of how the request is authorized: a Bearer token, a header of its own, or nothing. */
export function authOf(tool: HttpTool): { scheme: AuthScheme; secret: string; header: string } {
  const bearer = tool.headers.find((one) => one.name.toLowerCase() === "authorization" && /^Bearer \{\{secrets\.\w+\}\}$/.test(one.value));
  if (bearer !== undefined) return { scheme: "bearer", secret: secretIn(bearer.value), header: bearer.name };
  const own = tool.headers.find((one) => /^\{\{secrets\.\w+\}\}$/.test(one.value));
  if (own !== undefined) return { scheme: "header", secret: secretIn(own.value), header: own.name };
  return { scheme: "none", secret: "", header: "X-API-Key" };
}

/** The headers with the authorization chosen in place of the one there was, if any. */
export function withAuth(tool: HttpTool, scheme: AuthScheme, secret: string, header: string): HttpTool["headers"] {
  const was = authOf(tool);
  const kept = tool.headers.filter((one) => !(was.scheme !== "none" && one.name === was.header && one.value.includes(`{{secrets.${was.secret}}}`)));
  if (scheme === "none" || secret === "") return kept;
  if (scheme === "bearer") return [{ name: "Authorization", value: `Bearer {{secrets.${secret}}}` }, ...kept];
  return [{ name: header || "X-API-Key", value: `{{secrets.${secret}}}` }, ...kept];
}

function secretIn(value: string): string {
  return /\{\{secrets\.(\w+)\}\}/.exec(value)?.[1] ?? "";
}

/** The value of a static field as it is typed: a number or true/false typed as one, anything else text. */
export function fixedValueOf(typed: string): FixedField["value"] {
  if (typed === "true") return true;
  if (typed === "false") return false;
  return /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(typed) ? Number(typed) : typed;
}
