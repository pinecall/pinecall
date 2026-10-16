/** `@state`: declare which fields are state and who may see them. */

import { DeclarationRefused } from "./tools.js";

/** Who may see a state field (wire values from the protocol). */
export type Visibility = "public" | "tenant" | "pii";

/** Options for `@state({...})`. */
export interface StateOptions {
  visibility?: Visibility;
  /** Shorthand for `visibility: "pii"`. */
  pii?: boolean;
}

/** One field's declaration as carried in `AgentConfig.state_fields`. */
export interface StateFieldSpec {
  name: string;
  visibility: Visibility;
}

// Keyed by prototype; subclasses inherit by walking the chain. `undefined` visibility means the
// field is state and the wire default applies.
const declared = new WeakMap<object, Map<string, Visibility | undefined>>();

// Cached: decorators all run at class definition, and the Proxy reads this on every assignment.
const merged = new WeakMap<Function, ReadonlySet<string> | null>();

/**
 * Declare a field as state, optionally with its visibility: `@state`, `@state({ pii: true })`,
 * `@state({ visibility: "public" })`. The default visibility is `tenant`.
 */
export function state(prototype: object, name: string): void;
export function state(options?: StateOptions): (prototype: object, name: string) => void;
export function state(
  first?: object | StateOptions,
  name?: string,
): void | ((prototype: object, name: string) => void) {
  // Bare decorator `(prototype, name)` vs factory `(options?)`: told apart by the second argument.
  if (typeof name === "string") return declare(first as object, name, {});
  const options = (first ?? {}) as StateOptions;
  return (prototype, field) => declare(prototype, field, options);
}

/**
 * Field visibilities from `@state` decorators up the chain (parents first), then
 * `static visibility`, which wins.
 */
export function visibilityOf(ctor: Function): StateFieldSpec[] {
  const fields = new Map<string, Visibility | undefined>();
  for (const prototype of chainOf(ctor)) {
    for (const [field, visibility] of declared.get(prototype) ?? []) fields.set(field, visibility);
  }
  const map = (ctor as { visibility?: Record<string, Visibility> }).visibility;
  for (const [field, visibility] of Object.entries(map ?? {})) fields.set(field, visibility);
  return [...fields]
    .filter((entry): entry is [string, Visibility] => entry[1] !== undefined)
    .map(([name, visibility]) => ({ name, visibility }));
}

/**
 * The `@state` fields of a class, or null when it decorates none (then every own field is state).
 * Once any field is decorated, undecorated fields are excluded from snapshots, prompt and
 * `state.changed`. `static visibility` does not declare state.
 */
export function declaredStateOf(ctor: Function): ReadonlySet<string> | null {
  const known = merged.get(ctor);
  if (known !== undefined) return known;
  const fields = new Set<string>();
  for (const prototype of chainOf(ctor)) {
    for (const field of (declared.get(prototype) ?? new Map()).keys()) fields.add(field);
  }
  const answer = fields.size === 0 ? null : fields;
  merged.set(ctor, answer);
  return answer;
}

// Parents first, so a subclass's declarations override.
function chainOf(ctor: Function): object[] {
  const chain: object[] = [];
  for (
    let prototype: object | null = (ctor as { prototype?: object }).prototype ?? null;
    prototype !== null && prototype !== Object.prototype;
    prototype = Object.getPrototypeOf(prototype) as object | null
  ) {
    chain.unshift(prototype);
  }
  return chain;
}

function declare(prototype: object, name: string, options: StateOptions): void {
  let own = declared.get(prototype);
  if (own === undefined) {
    own = new Map<string, Visibility | undefined>();
    declared.set(prototype, own);
  }
  own.set(name, visibilityIn(options, prototype, name));
}

// Refuse `pii: true` combined with a different `visibility`.

function visibilityIn(options: StateOptions, prototype: object, name: string): Visibility | undefined {
  if (options.pii === true && options.visibility !== undefined && options.visibility !== "pii") {
    throw new DeclarationRefused(
      `@state({ pii: true, visibility: ${JSON.stringify(options.visibility)} }) on ` +
        `${(prototype as { constructor: Function }).constructor.name}.${name}: ` +
        `two different answers to one question; write one`,
    );
  }
  if (options.pii === true) return "pii";
  return options.visibility;
}
