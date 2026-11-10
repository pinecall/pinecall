/** Quality's doors: the judges a call meets, the case groups and their fixes, the cases waiting, and each agent's newest golden run. */

import { z } from "zod";

import { post, read, type Credentials } from "@pinecall/core/api";
import { CaseGroupListSchema, EvalCaseListSchema, JudgeListSchema, type CaseGroup, type EvalCase, type JudgeRow, type Proposal } from "@pinecall/core/wire/rest-evals";

export type { CaseGroup, EvalCase, JudgeRow, Proposal };

/** The owner the runtime gives Pinecall's own judges. */
export const PINECALL = "pinecall";

const named = encodeURIComponent;

/** The judges of one agent's calls, or with "" the org's: Pinecall's as switched, then the org's own. */
export async function readJudges(credentials: Credentials, agent: string): Promise<JudgeRow[]> {
  const door = agent === "" ? "/v1/org/judges" : `/v1/agents/${named(agent)}/judges`;
  return JudgeListSchema.parse(await read(credentials, door)).judges;
}

/** The case groups of one agent, or of every agent when it is "", the pending first. */
export async function readGroups(credentials: Credentials, agent: string): Promise<CaseGroup[]> {
  return CaseGroupListSchema.parse(await read(credentials, "/v1/evals/groups", agent === "" ? {} : { agent })).groups;
}

/** The cases of one agent, or of every agent when it is "", the pending first. */
export async function readCases(credentials: Credentials, agent: string): Promise<EvalCase[]> {
  return EvalCaseListSchema.parse(await read(credentials, "/v1/evals/cases", agent === "" ? {} : { agent })).cases;
}

/** A group's proposed setting written as a new version of the agent's settings. */
export async function applyGroup(credentials: Credentials, id: string): Promise<void> {
  await post(credentials, `/v1/evals/groups/${named(id)}/apply`, {});
}

const RunsSchema = z.looseObject({
  runs: z.array(
    z.looseObject({
      agent: z.string(),
      status: z.string(),
      matrix: z.looseObject({ runs: z.array(z.looseObject({ scores: z.array(z.looseObject({ passed: z.boolean() })) })) }).nullable(),
    }),
  ),
});

/** An agent's newest golden run that finished: how many of its goldens held, of how many played. */
export interface Suite {
  agent: string;
  held: number;
  cells: number;
}

// The door's own most.
const AS_MANY_AS_IT_GIVES = 200;

/** The newest finished run of each agent, out of every run of this world, which the door gives newest first. */
export async function readSuites(credentials: Credentials): Promise<Suite[]> {
  const { runs } = RunsSchema.parse(await read(credentials, "/v1/evals/runs", { limit: AS_MANY_AS_IT_GIVES }));
  const found = new Map<string, Suite>();
  for (const run of runs) {
    if (found.has(run.agent) || run.status !== "done" || run.matrix === null) continue;
    const cells = run.matrix.runs;
    found.set(run.agent, { agent: run.agent, cells: cells.length, held: cells.filter((cell) => cell.scores.every((score) => score.passed)).length });
  }
  return [...found.values()];
}
