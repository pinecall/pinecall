/** Read a class's JSDoc and parameter types from its source at runtime, with oxc's parser. */

import { parseSync } from "oxc-parser";
import type {
  Class,
  ClassElement,
  Comment,
  FormalParameter,
  ParamPattern,
  Statement,
  TSInterfaceDeclaration,
  TSSignature,
  TSType,
  TSTypeAliasDeclaration,
} from "oxc-parser";

// Transpiled class bodies keep their JSDoc, so `Ctor.toString()` yields docs and parameter names;
// types are erased, so describe() takes the real .ts source when it is available.
// oxc, not TypeScript: TS 7 (the Go port) ships no JS parser, and regexes cannot follow types.

/** One parameter of a tool method, as the source declares it. */
export interface ParamDoc {
  name: string;
  type?: string;
  optional: boolean;
  /** JSON Schema for an interface or type literal; unset when `type` alone suffices (`string`, `number[]`). */
  schema?: Record<string, unknown>;
}

/** A class's docstring and its methods' docstrings and parameters. */
export interface ClassDocs {
  doc?: string;
  methods: Map<string, { doc?: string; params: ParamDoc[] }>;
}

const registered = new WeakMap<Function, ClassDocs>();
const scraped = new WeakMap<Function, ClassDocs>();

/** Interfaces and type aliases declared in the same file, by name. */
type Declared = Map<string, TSInterfaceDeclaration | TSTypeAliasDeclaration>;

/** Schema for a type whose shape is not visible in this file. */
const ANY_OBJECT = { type: "object", additionalProperties: true } as const;

/** Source text and its JSDoc blocks. */
interface Source {
  text: string;
  jsdoc: Comment[];
}

/** Flatten a JSDoc's description into one line, dropping tags. */
function oneLine(value: string): string | undefined {
  const lines: string[] = [];
  for (const raw of value.split("\n")) {
    let line = raw.trim();
    while (line.startsWith("*")) line = line.slice(1).trim();
    // The first tag line ends the description.
    if (line.startsWith("@")) break;
    if (line.length > 0) lines.push(line);
  }
  const flat = lines.join(" ");
  return flat.length > 0 ? flat : undefined;
}

/**
 * The JSDoc block ending right above `start`, separated only by whitespace. Method decorators are
 * inside the node's span, so decorated methods still match.
 */
function docAt(start: number, source: Source): string | undefined {
  let found: Comment | undefined;
  for (const comment of source.jsdoc) {
    if (comment.end > start) break;
    if (source.text.slice(comment.end, start).trim().length === 0) found = comment;
  }
  return found ? oneLine(found.value) : undefined;
}

/** The type's source text. */
function textOf(node: TSType, source: Source): string {
  return source.text.slice(node.start, node.end);
}

/** The declaration inside an `export`, or the statement itself. */
function declarationOf(statement: Statement): Statement {
  if (statement.type === "ExportNamedDeclaration" && statement.declaration) return statement.declaration;
  if (statement.type === "ExportDefaultDeclaration") return statement.declaration as Statement;
  return statement;
}

/** Top-level interfaces and type aliases. */
function declaredTypes(body: Statement[]): Declared {
  const types: Declared = new Map();
  for (const statement of body) {
    const declared = declarationOf(statement);
    if (declared.type === "TSInterfaceDeclaration" || declared.type === "TSTypeAliasDeclaration") {
      types.set(declared.id.name, declared);
    }
  }
  return types;
}

/** The default-exported class, else the first class, with the position its docstring must end at. */
function theClass(body: Statement[]): { node: Class; start: number } | undefined {
  let first: { node: Class; start: number } | undefined;
  for (const statement of body) {
    const declared = declarationOf(statement);
    if (declared.type !== "ClassDeclaration" && declared.type !== "ClassExpression") continue;
    const found = { node: declared as Class, start: docstringEnd(declared, statement.start) };
    if (statement.type === "ExportDefaultDeclaration") return found;
    first ??= found;
  }
  return first;
}

// A decorated class's docstring sits above its first decorator, which precedes the statement start.
function docstringEnd(declared: { decorators?: { start: number }[] }, start: number): number {
  const decorators = declared.decorators ?? [];
  return decorators.reduce((earliest, decorator) => Math.min(earliest, decorator.start), start);
}

/** `undefined` or `null` in a union: makes the parameter optional. */
function isNothing(node: TSType): boolean {
  return node.type === "TSUndefinedKeyword" || node.type === "TSNullKeyword";
}

/** JSON Schema for a type, following aliases declared in the same file. */
function jsonOf(node: TSType, types: Declared, seen: Set<string>): Record<string, unknown> {
  if (node.type === "TSStringKeyword") return { type: "string" };
  if (node.type === "TSNumberKeyword") return { type: "number" };
  if (node.type === "TSBooleanKeyword") return { type: "boolean" };
  // The model never supplies a callback.
  if (node.type === "TSFunctionType") return { description: "callback" };
  if (node.type === "TSArrayType") return { type: "array", items: jsonOf(node.elementType, types, seen) };
  if (node.type === "TSParenthesizedType") return jsonOf(node.typeAnnotation, types, seen);
  if (node.type === "TSTypeLiteral") return objectOf(node.members, types, seen);
  if (node.type === "TSUnionType") return unionOf(node.types, types, seen);
  if (node.type === "TSLiteralType") return literalOf(node);
  if (node.type === "TSTypeReference" && node.typeName.type === "Identifier") {
    return referenceOf(node.typeName.name, types, seen);
  }
  return { ...ANY_OBJECT };
}

/** Expand a type name declared in this file; other names become a described object. */
function referenceOf(name: string, types: Declared, seen: Set<string>): Record<string, unknown> {
  // Stop on recursive types.
  const declared = seen.has(name) ? undefined : types.get(name);
  if (!declared) return { type: "object", description: name };
  const deeper = new Set(seen).add(name);
  if (declared.type === "TSInterfaceDeclaration") return objectOf(declared.body.body, types, deeper);
  return jsonOf(declared.typeAnnotation, types, deeper);
}

/** Object schema for interface or type-literal members. */
function objectOf(members: TSSignature[], types: Declared, seen: Set<string>): Record<string, unknown> {
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  for (const member of members) {
    if (member.type !== "TSPropertySignature" || member.key.type !== "Identifier") continue;
    const type = member.typeAnnotation?.typeAnnotation;
    properties[member.key.name] = type ? jsonOf(type, types, seen) : { ...ANY_OBJECT };
    if (!member.optional) required.push(member.key.name);
  }
  return { type: "object", properties, required, additionalProperties: false };
}

/** A literal type's value, or undefined for templates and expressions. */
function valueOf(node: TSType): unknown {
  if (node.type !== "TSLiteralType") return undefined;
  return "value" in node.literal ? node.literal.value : undefined;
}

/** A union of string literals becomes an enum; anything else an open object. */
function unionOf(members: TSType[], types: Declared, seen: Set<string>): Record<string, unknown> {
  const real = members.filter((one) => !isNothing(one));
  if (real.length === 1 && real[0]) return jsonOf(real[0], types, seen);
  const values = real.map(valueOf).filter((value) => typeof value === "string");
  if (values.length === real.length && real.length > 0) return { type: "string", enum: values };
  return { ...ANY_OBJECT };
}

/** Schema for a literal type. */
function literalOf(node: TSType): Record<string, unknown> {
  const value = valueOf(node);
  if (typeof value === "string") return { type: "string", enum: [value] };
  if (typeof value === "number") return { type: "number" };
  if (typeof value === "boolean") return { type: "boolean" };
  return { ...ANY_OBJECT };
}

/** Types the registry maps from text alone, so no schema is attached. */
function plainType(node: TSType): boolean {
  if (node.type === "TSStringKeyword") return true;
  if (node.type === "TSNumberKeyword") return true;
  if (node.type === "TSBooleanKeyword") return true;
  if (node.type === "TSFunctionType") return true;
  return node.type === "TSArrayType" && plainType(node.elementType);
}

/** One parameter's name, type text and optionality. */
function paramOf(node: ParamPattern, source: Source, types: Declared): ParamDoc | undefined {
  const defaulted = node.type === "AssignmentPattern";
  const binding = (defaulted ? node.left : node) as FormalParameter;
  // Destructured parameters have no name to offer the model.
  if (binding.type !== "Identifier") return undefined;
  let type = binding.typeAnnotation?.typeAnnotation;
  let optional = defaulted || Boolean(binding.optional);
  if (type?.type === "TSUnionType") {
    const real = type.types.filter((one) => !isNothing(one));
    if (real.length < type.types.length) optional = true;
    if (real.length === 1 && real[0]) type = real[0];
  }
  const param: ParamDoc = { name: binding.name, optional };
  if (type) param.type = textOf(type, source);
  if (type && !plainType(type)) param.schema = jsonOf(type, types, new Set());
  return param;
}

/** Parameters of a method, or of a function-valued field. */
function paramsOf(member: ClassElement, source: Source, types: Declared): ParamDoc[] {
  const holder =
    member.type === "MethodDefinition"
      ? member.value
      : member.type === "PropertyDefinition" &&
          (member.value?.type === "ArrowFunctionExpression" || member.value?.type === "FunctionExpression")
        ? member.value
        : undefined;
  if (!holder || holder.type === "TSEmptyBodyFunctionExpression") return [];
  return holder.params.map((param) => paramOf(param, source, types)).filter((param) => param !== undefined);
}

/**
 * Read a class's JSDoc and method signatures from source text: a full file, or `Ctor.toString()`.
 * `file`'s extension selects the dialect: JSX fails as .ts, and `<T>x` casts fail as .tsx.
 */
export function parseClassSource(text: string, file = "agent.tsx"): ClassDocs {
  const docs: ClassDocs = { methods: new Map() };
  const parsed = parseSync(file, text, { sourceType: "module" });
  const source: Source = {
    text,
    jsdoc: parsed.comments.filter((one) => one.type === "Block" && one.value.startsWith("*")),
  };
  const body = parsed.program.body as Statement[];
  const found = theClass(body);
  if (!found) return docs;
  const doc = docAt(found.start, source);
  if (doc) docs.doc = doc;
  const types = declaredTypes(body);
  for (const member of found.node.body.body) {
    const method = member.type === "MethodDefinition" && (member.kind === "method" || member.kind === "get");
    if (!method && member.type !== "PropertyDefinition") continue;
    if (member.key.type !== "Identifier") continue;
    const name = member.key.name;
    if (docs.methods.has(name)) continue;
    const entry: { doc?: string; params: ParamDoc[] } = { params: paramsOf(member, source, types) };
    const memberDoc = docAt(member.start, source);
    if (memberDoc) entry.doc = memberDoc;
    docs.methods.set(name, entry);
  }
  return docs;
}

// Bumped by describe() so caches built from scraped bodies know they are stale.
let version = 0;

/** Counter bumped by each describe(); used to invalidate caches. */
export function docsVersion(): number {
  return version;
}

/** Register a class's source so its docstrings and parameter types are available at runtime. */
export function describe(ctor: Function, source: string, file?: string): ClassDocs {
  const docs = parseClassSource(source, file);
  registered.set(ctor, docs);
  version++;
  return docs;
}

/** The class's docs, from describe() if called, else parsed from `ctor.toString()`. */
export function docsOf(ctor: Function): ClassDocs {
  const given = registered.get(ctor);
  if (given) return given;
  let own = scraped.get(ctor);
  if (!own) {
    own = parseClassSource(ctor.toString());
    scraped.set(ctor, own);
  }
  return own;
}

/** The class docstring, read from its source or from an explicit `static doc`. */
export function classDoc(ctor: Function): string | undefined {
  return docsOf(ctor).doc ?? (ctor as { doc?: string }).doc;
}

/** The class and its ancestors, most derived first, excluding Function.prototype. */

function chain(ctor: Function): Function[] {
  const classes: Function[] = [];
  for (let current: unknown = ctor; typeof current === "function"; current = Object.getPrototypeOf(current)) {
    if (current === Function.prototype) break;
    classes.push(current as Function);
  }
  return classes;
}

/** The docstring of one method, looked up along the prototype chain. */
export function methodDoc(ctor: Function, name: string): string | undefined {
  for (const current of chain(ctor)) {
    const doc = docsOf(current).methods.get(name)?.doc;
    if (doc) return doc;
  }
  return undefined;
}

/** The parameters of one method, looked up along the prototype chain. */
export function methodParams(ctor: Function, name: string): ParamDoc[] {
  for (const current of chain(ctor)) {
    const found = docsOf(current).methods.get(name);
    if (found) return found.params;
  }
  return [];
}
