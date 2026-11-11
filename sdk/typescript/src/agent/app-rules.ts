/** The rules a voice app gives every agent of it: kept per class, read into the prompt's identity block. */

// Keyed by class, as the tools' registries are: a mount says them once and every instance reads them.
const rules = new WeakMap<Function, readonly string[]>();

/** Say the rules the app gives this class; an empty list takes them away. */
export function setAppRules(ctor: Function, given: readonly string[]): void {
  rules.set(ctor, [...given]);
}

/** The rules the app gave an instance's class, one per line; empty for an agent of no app. */
export function appRulesOf(agent: object): string {
  return (rules.get((agent as { constructor: Function }).constructor) ?? []).map((rule) => `- ${rule}`).join("\n");
}
