/** A team of agents one call passes between: the tools that offer the pass, and every tool such a call may open. */

import type { ToolSpec } from "../wire/defs.js";

import type { Agent } from "../agent/agent.js";
import { DeclarationRefused } from "../agent/tools.js";
import type { CallLine } from "../call/call.js";

type Ctor = new () => Agent;

/** The agents a call may pass between, each with the slug it is served as. */
export type Team = ReadonlyMap<Ctor, string>;

/** How many times one call is passed before the next pass is refused: two agents never hand it back and forth all day. */
export const MOST_PASSES = 3;

/** The custom entry a pass leaves on its call. */
export const PASSED = "handoff";

/** The custom entry a call leaves when its line's `answers` chose who serves it, or could not. */
export const ROUTED = "routed";

/** How long a line's `answers` has to choose: the caller is hearing the greeting meanwhile. */
export const ANSWERED_WITHIN_MS = 1000;

/** A line's `answers` as a function: the agent of the team that serves this call, or nothing for the one it is bound to. */
export type Answering = (call: CallLine) => Ctor | undefined | Promise<Ctor | undefined>;

const TRANSFER = "transfer_to_";
const LATE = Symbol("late");

/**
 * Who serves a call whose line chooses: what `answers` returned when it is of the team and came in
 * time, else `bound`, the agent the number is pointed at, with why. It never throws: a call is answered.
 */
export async function answeredBy(answers: Answering, line: CallLine, bound: Ctor, team: Team): Promise<{ agent: Ctor; why?: string }> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<typeof LATE>((resolve) => (timer = setTimeout(() => resolve(LATE), ANSWERED_WITHIN_MS)));
  try {
    const chosen = await Promise.race([Promise.resolve().then(() => answers(line)), late]);
    if (chosen === LATE) return { agent: bound, why: `answers took more than ${ANSWERED_WITHIN_MS} ms` };
    if (chosen === undefined || chosen === bound) return { agent: bound };
    if (!team.has(chosen)) return { agent: bound, why: `answers chose ${String((chosen as Function).name)}, which is not of the line's team` };
    return { agent: chosen };
  } catch (failed) {
    return { agent: bound, why: `answers threw: ${failed instanceof Error ? failed.message : String(failed)}` };
  } finally {
    clearTimeout(timer);
  }
}

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

// What the model reads once the call is the teammate's. It called a tool named for a transfer, and a small
// model goes on as whoever transfers ("one moment while I connect you") and then waits: measured on
// gemini-3.5-flash-lite, half the passes ended that way under "go on as …, without saying it was passed",
// and one in sixteen under this.
/** The transfer tool's result: the call is the teammate's, and the caller waits for an answer. */
export const passedTo = (slug: string): string =>
  `Done: you are ${slug} now, and the caller is already talking to you. There is nobody left to connect them to, so never say "one moment" or that you are connecting or transferring them. Reply to their last message now, as ${slug}.`;
