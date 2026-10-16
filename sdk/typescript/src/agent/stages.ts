/** `stage`: shorthand for a tool visible only in certain stages of the agent. */

import type { Snapshot } from "./state.js";
import type { ToolOptions } from "./tools.js";

/**
 * Type for an agent's `stage` field: `stage: Stages<"identify" | "book"> = "identify"`.
 * It is an ordinary state field; `@tool({ stage })` is typed against it.
 */
export type Stages<Named extends string> = Named;

/**
 * The union declared by a class's `stage` field, or `never` if it has none, so a misspelled or
 * undeclared stage in `@tool({ stage })` is a compile error.
 */
export type StageOf<T> = T extends { stage: infer Named extends string } ? Named : never;

/** A declaration's `stage` option normalized to a list. */
export function stagesOf(options: { stage?: unknown }): string[] | undefined {
  const declared = options.stage;
  if (declared === undefined) return undefined;
  return Array.isArray(declared) ? declared.map(String) : [String(declared)];
}

/** The agent's current stage, or undefined if it has no string `stage` field. */
export function stageOf(agent: object): string | undefined {
  const named = (agent as { stage?: unknown }).stage;
  return typeof named === "string" ? named : undefined;
}

/** Convert `stage` into a `when` predicate, AND-ed with any `when` already given. */

export function lowerStage<T extends object>(options: ToolOptions<T>): ToolOptions<T> {
  const stages = stagesOf(options);
  if (stages === undefined) return options;
  const also = options.when;
  const inOneOfThem = (state: Snapshot<T>): boolean => {
    const named = (state as { stage?: unknown }).stage;
    return typeof named === "string" && stages.includes(named);
  };
  return {
    ...options,
    when: also === undefined ? inOneOfThem : (state) => inOneOfThem(state) && also(state),
  };
}
