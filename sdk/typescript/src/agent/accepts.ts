/** `static events`: the external events a class accepts, and from which senders. */

/** Event sender: the tenant's backend (`app`) or a participant's browser. */
export type EventSource = "app" | "participant";

/** One accepted event. Only senders listed in `from` reach the hook. */
export interface EventDecl {
  from: EventSource[];
}

/** A class's event declarations, e.g. `{ "cart.changed": { from: ["app"] } }`. */
export type EventDeclarations = Record<string, EventDecl>;

/** One declaration as carried in `AgentConfig.events`. */
export interface EventSpec {
  name: string;
  from: EventSource[];
}

/** Event metadata: sender, participant identity if any, and log sequence number. */
export interface EventMeta {
  source: EventSource;
  identity?: string;
  seq: number;
}

/**
 * Every event the class declares, parents first. A subclass redeclaring a name replaces its
 * senders instead of merging them.
 */
export function eventsOf(ctor: Function): EventSpec[] {
  const merged = new Map<string, EventSource[]>();
  const chain: Function[] = [];
  for (let step: Function | null = ctor; typeof step === "function"; step = Object.getPrototypeOf(step) as Function | null) {
    chain.unshift(step);
  }
  for (const step of chain) {
    const own = Object.getOwnPropertyDescriptor(step, "events")?.value as EventDeclarations | undefined;
    for (const [name, decl] of Object.entries(own ?? {})) merged.set(name, [...decl.from]);
  }
  return [...merged].map(([name, from]) => ({ name, from }));
}

/**
 * Whether the class accepts `name` from `source`. The gateway checks this too; the runtime
 * rechecks because a replayed log must not run a hook on an undeclared event.
 */

export function accepts(ctor: Function, name: string, source: EventSource): boolean {
  const declared = eventsOf(ctor).find((spec) => spec.name === name);
  return declared !== undefined && declared.from.includes(source);
}
