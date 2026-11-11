/** A team of agents one call passes between: the tools that offer the pass, and every tool such a call may open. */

import type { ToolSpec } from "../wire/defs.js";

import type { Agent } from "../agent/agent.js";
import { DeclarationRefused } from "../agent/tools.js";

type Ctor = new () => Agent;

/** The agents a call may pass between, each with the slug it is served as. */
export type Team = ReadonlyMap<Ctor, string>;

/** How many times one call is passed before the next pass is refused: two agents never hand it back and forth all day. */
export const MOST_PASSES = 3;

/** The custom entry a pass leaves on its call. */
export const PASSED = "handoff";

const TRANSFER = "transfer_to_";

/** What a class says it takes, in the words a model reads to choose it; undefined when it takes no passes. */
export function takenBy(ctor: Function): string | undefined {
  const takes = (ctor as { takes?: unknown }).takes;
  return typeof takes === "string" && takes.trim() !== "" ? takes.trim() : undefined;
}

/** The tools that offer the call of `ctor` to each teammate that says what it takes. */
export function transfersOf(ctor: Function, team: Team): ToolSpec[] {
  const offered: ToolSpec[] = [];
  for (const mate of team.keys()) {
    const takes = takenBy(mate);
    if (mate === ctor || takes === undefined) continue;
    offered.push({
      name: transferName(mate),
      description: `Pass the call to ${mate.name}, who takes ${takes}. Call it as soon as the caller brings that up: do not ask them first, and do not answer it yourself. The caller is not told about the pass.`,
      parameters: {
        type: "object",
        properties: { reason: { type: "string", description: "Why the call is passed, in a few words." } },
        required: [],
      },
    });
  }
  return offered;
}

/** The teammate a transfer tool names. */
export function mateNamed(tool: string, team: Team): Ctor | undefined {
  for (const mate of team.keys()) if (transferName(mate) === tool) return mate;
  return undefined;
}

/**
 * Every tool a call of the team may open: each member's own and every transfer. They are declared
 * once per agent, since the gateway keeps a call's tools as its agent declared them. A name two
 * members declare is refused: the model would call one and the other would answer.
 */
export function teamTools(team: Team): ToolSpec[] {
  const owners = new Map<string, string>();
  const declared: ToolSpec[] = [];
  for (const [member, slug] of team) {
    for (const spec of [...new member().tools(), ...transfersOf(member, team)]) {
      const owner = owners.get(spec.name);
      if (owner === slug || (owner !== undefined && spec.name.startsWith(TRANSFER))) continue;
      if (owner !== undefined) throw new DeclarationRefused(`${owner} and ${slug} both declare a tool named ${spec.name}: the agents of one team give each tool a name of its own`);
      owners.set(spec.name, slug);
      declared.push(spec);
    }
  }
  return declared;
}

// Named by the class, not by the slug: a slug is one org's in the whole gateway, and a tool's name is the model's to read.
function transferName(mate: Function): string {
  return `${TRANSFER}${mate.name.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase()}`;
}
