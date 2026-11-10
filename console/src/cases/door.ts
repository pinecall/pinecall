/** The cases' doors: the org's cases and the groups a judge's breaks fall in, a group diagnosed, fixed or decided, and one case played again on a version of the settings. */

import { z } from "zod";

import { patch, post, read, type Credentials } from "@pinecall/core/api";
import { CaseGroupListSchema, CaseGroupSchema, EvalCaseListSchema, type CaseDecision, type CaseGroup, type EvalCase, type Proposal } from "@pinecall/core/wire/rest-evals";
import { TuningHistorySchema, type TuningRow } from "@pinecall/core/wire/rest-org";

export type { CaseDecision, CaseGroup, EvalCase, Proposal, TuningRow };

const named = encodeURIComponent;
const whose = (agent: string): Record<string, string> => (agent === "" ? {} : { agent });
const groupAt = (id: string): string => `/v1/evals/groups/${named(id)}`;

/** The cases of one agent, or of every agent with "", the pending first, and how many wait of how many may. */
export interface Listed {
  cases: EvalCase[];
  pending: number;
  pendingAtMost: number;
}

export async function readCases(credentials: Credentials, agent: string): Promise<Listed> {
  const listed = EvalCaseListSchema.parse(await read(credentials, "/v1/evals/cases", whose(agent)));
  return { cases: listed.cases, pending: listed.pending, pendingAtMost: listed.pending_at_most };
}

export async function readGroups(credentials: Credentials, agent: string): Promise<CaseGroup[]> {
  return CaseGroupListSchema.parse(await read(credentials, "/v1/evals/groups", whose(agent))).groups;
}

/** The group diagnosed on the judge model: the cause its calls share, and the change proposed. One eval. */
export async function diagnoseGroup(credentials: Credentials, id: string): Promise<CaseGroup> {
  return CaseGroupSchema.parse(await post(credentials, `${groupAt(id)}/propose`, {}));
}

/** A proposed setting written as a new version of the person's own settings. */
export async function applyGroup(credentials: Credentials, id: string): Promise<void> {
  await post(credentials, `${groupAt(id)}/apply`, {});
}

/** A caller like the group's newest one, kept as the agent's own for simulations. One eval. */
export async function callerFromGroup(credentials: Credentials, id: string): Promise<void> {
  await post(credentials, `${groupAt(id)}/persona`, {});
}

/** The group and every case waiting in it approved or dismissed; dismissed, the judge may be told it was wrong. */
export async function decideGroup(credentials: Credentials, id: string, decision: { status: "approved" | "dismissed"; judge_was_wrong?: boolean }): Promise<CaseGroup> {
  return CaseGroupSchema.parse(await patch(credentials, groupAt(id), decision));
}

/** The person's own versions of the agent's settings, newest first: what a fix is saved as before anybody else hears it. */
export async function readVersions(credentials: Credentials, agent: string): Promise<TuningRow[]> {
  return TuningHistorySchema.parse(await read(credentials, `/v1/agents/${named(agent)}/settings/history`, { team: "false" })).rows;
}

const ScoreSchema = z.looseObject({ metric: z.string(), passed: z.boolean(), reason: z.string() });
const RunSchema = z.looseObject({
  id: z.string(),
  // `failed` is the run itself breaking; a case that broke is a score, not a status.
  status: z.enum(["running", "done", "failed"]),
  calls: z.array(z.looseObject({ golden: z.string(), call: z.string() })),
  matrix: z.looseObject({ runs: z.array(z.looseObject({ golden: z.string(), scores: z.array(ScoreSchema) })) }).nullable(),
  error: z.string().nullable(),
});
export type Run = z.infer<typeof RunSchema>;

/** One case played through whatever holds the agent, on a version of the person's settings or as they stand; answered at once, still running. */
export async function playCase(credentials: Credentials, agent: string, name: string, version: number | null): Promise<Run> {
  return RunSchema.parse(await post(credentials, "/v1/evals/run", { agent, cases: [name], ...(version === null ? {} : { version }) }));
}

export async function readRun(credentials: Credentials, id: string): Promise<Run> {
  return RunSchema.parse(await read(credentials, `/v1/evals/runs/${named(id)}`));
}
