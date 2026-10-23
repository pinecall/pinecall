/** Cases doors: the org's dataset read for one agent, a call kept as a case, one written by hand, and what a person decides. */

import {
  type CaseDecision,
  type CaseGroup,
  CaseGroupListSchema,
  CaseGroupSchema,
  type EvalCase,
  EvalCaseListSchema,
  EvalCaseSchema,
  type GeneratedPersonas,
  GeneratedPersonasSchema,
  type Proposal,
  type WriteCase,
} from "@pinecall/core/wire/rest-evals";

import { patch, post, put, read, type Credentials } from "@pinecall/core/api";

export type { CaseDecision, CaseGroup, EvalCase, Proposal, WriteCase };

const groupDoor = (id: string): string => `/v1/evals/groups/${encodeURIComponent(id)}`;

/** The org's case groups, one agent's or every one's when "", the pending first. */
export async function readGroups(credentials: Credentials, agent: string): Promise<CaseGroup[]> {
  return CaseGroupListSchema.parse(await read(credentials, "/v1/evals/groups", agent === "" ? {} : { agent })).groups;
}

/** The group diagnosed on the judge model: the cause its calls share, and the fix proposed. One eval. */
export async function proposeGroup(credentials: Credentials, id: string): Promise<CaseGroup> {
  return CaseGroupSchema.parse(await post(credentials, `${groupDoor(id)}/propose`, {}));
}

/** A proposed setting written as a new version of the person's own settings. */
export async function applyGroup(credentials: Credentials, id: string): Promise<void> {
  await post(credentials, `${groupDoor(id)}/apply`, {});
}

/** A persona like the group's newest caller, kept as the agent's own. One eval. */
export async function personaFromGroup(credentials: Credentials, id: string): Promise<GeneratedPersonas> {
  return GeneratedPersonasSchema.parse(await post(credentials, `${groupDoor(id)}/persona`, {}));
}

/** Approve or dismiss a group and every case waiting in it. */
export async function decideGroup(credentials: Credentials, id: string, decision: { status: "approved" | "dismissed"; judge_was_wrong?: boolean }): Promise<CaseGroup> {
  return CaseGroupSchema.parse(await patch(credentials, groupDoor(id), decision));
}

/** One agent's cases, the pending first, and how many wait of how many may. */
export interface Listed {
  cases: EvalCase[];
  pending: number;
  pendingAtMost: number;
}

/** Every case of one agent, or of every agent when it is "", whatever its status: the gateway orders the pending first. */
export async function readCases(credentials: Credentials, agent: string): Promise<Listed> {
  const listed = EvalCaseListSchema.parse(await read(credentials, "/v1/evals/cases", agent === "" ? {} : { agent }));
  return { cases: listed.cases, pending: listed.pending, pendingAtMost: listed.pending_at_most };
}

/** Write what a person decided of one case; resolves to the case as it stands now. */
export async function decideCase(credentials: Credentials, id: string, decision: CaseDecision): Promise<EvalCase> {
  return EvalCaseSchema.parse(await patch(credentials, `/v1/evals/cases/${encodeURIComponent(id)}`, decision));
}

/**
 * Keep a finished call as a case of the org's dataset, approved from the start: a person kept it.
 * Its expect is what the call's broken verdicts give; a call that held expects nothing yet.
 */
export async function keepCall(credentials: Credentials, call: string, name: string): Promise<EvalCase> {
  return EvalCaseSchema.parse(await post(credentials, "/v1/evals/cases", { call, name }));
}

/**
 * Write a golden as a case of the agent, approved from the start: a person wrote it, so no call is
 * behind it. The same name again rewrites a case the person wrote; one a call made is refused (409).
 */
export async function writeCase(credentials: Credentials, agent: string, name: string, body: WriteCase): Promise<EvalCase> {
  return EvalCaseSchema.parse(await put(credentials, `/v1/agents/${encodeURIComponent(agent)}/cases/${encodeURIComponent(name)}`, body));
}
