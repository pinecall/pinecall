/** The org's dataset: real calls kept as cases — read, decided, pulled into the repository, kept, forgotten — and the groups they fall into. */

import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { z } from "zod";

import * as api from "../../api/cases.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";

export type { CaseGroup, CaseStatus, EvalCase, GeneratedPersonas, Proposal } from "../../api/cases.js";

export const STATUSES: readonly api.CaseStatus[] = ["pending", "approved", "dismissed"];

/** The note goes on the judge's calibration label; with no judge it would be dropped. */
export const A_NOTE_ALONE = "note is kept on the judge's calibration label, so it goes with the judge that was wrong";

/** The inbox: the agent's cases, the pending first, and how many wait of how many may. */
export interface CaseList {
  agent: string;
  cases: api.EvalCase[];
  pending: number;
  pending_at_most: number;
}

/** A case written into the repository: the file, and the case as it is marked now. */
export interface Pulled {
  path: string;
  case: api.EvalCase;
}

/** What `cases dismiss` takes: the judge that should have held, and why. */
export const DismissInput = z.object({
  judgeWasWrong: z.string().min(1).optional(),
  note: z.string().optional(),
});
export type DismissInput = z.infer<typeof DismissInput>;

/** What `cases keep` takes: a finished call, the name it is played by, whether only a run naming it plays it. */
export const KeepInput = z.object({
  call: z.string().min(1),
  name: z.string().trim().min(1, "keep names the case it makes: --name x, the name `pinecall test --case` plays it by"),
  heldOut: z.boolean().default(false),
});
export type KeepInput = z.infer<typeof KeepInput>;

/** Whether a name a person typed is a group's id rather than a case's name. */
export const isGroup = (named: string): boolean => named.startsWith("grp_");

export async function listCases(ctx: Context, agent: string, status?: api.CaseStatus): Promise<CaseList> {
  const sent = await api.listCases(ctx.gateway(), agent, status);
  return { agent, cases: sent.cases.map(whole), pending: sent.pending ?? 0, pending_at_most: sent.pending_at_most ?? 0 };
}

/** One of the agent's cases by its name; an unknown name is refused naming it. */
export async function getCase(ctx: Context, agent: string, name: string): Promise<api.EvalCase> {
  const found = (await listCases(ctx, agent)).cases.find((one) => one.name === name);
  if (found === undefined) throw new UsageError(`${agent} has no case named ${name}: \`pinecall cases\` lists them`);
  return found;
}

export async function approveCase(ctx: Context, agent: string, name: string): Promise<api.EvalCase> {
  return decide(ctx, agent, name, { status: "approved" });
}

export async function reopenCase(ctx: Context, agent: string, name: string): Promise<api.EvalCase> {
  return decide(ctx, agent, name, { status: "pending" });
}

export async function dismissCase(ctx: Context, agent: string, name: string, input: DismissInput): Promise<api.EvalCase> {
  if (input.note !== undefined && input.judgeWasWrong === undefined) throw new UsageError(`--${A_NOTE_ALONE}`);
  return decide(ctx, agent, name, {
    status: "dismissed",
    ...(input.judgeWasWrong === undefined ? {} : { judge_was_wrong: input.judgeWasWrong }),
    ...(input.note === undefined ? {} : { note: input.note }),
  });
}

/** A finished call kept as an approved case of the agent that took it. */
export async function keepCall(ctx: Context, input: KeepInput): Promise<api.EvalCase> {
  return whole(await api.createCase(ctx.gateway(), { call: input.call, name: input.name, ...(input.heldOut ? { held_out: true } : {}) }));
}

/** The case dropped; the call it came from stays. */
export async function forgetCase(ctx: Context, agent: string, name: string): Promise<api.EvalCase> {
  const found = await getCase(ctx, agent, name);
  await api.deleteCase(ctx.gateway(), found.id);
  return found;
}

/**
 * The case's golden written as `<name>.json` in `folder`, then marked kept in the repository, so the
 * nightly plays the file and not the case. The file is written first: a mark with no file would
 * leave the case played by nothing.
 */
export async function pullCase(ctx: Context, agent: string, name: string, folder: string): Promise<Pulled> {
  const found = await getCase(ctx, agent, name);
  await mkdir(folder, { recursive: true });
  const path = join(folder, `${found.name}.json`);
  await writeFile(path, `${JSON.stringify(found.golden, null, 2)}\n`, "utf8");
  return { path, case: whole(await api.patchCase(ctx.gateway(), found.id, { kept_in_repo: true })) };
}

export async function listGroups(ctx: Context, agent: string): Promise<api.CaseGroup[]> {
  return api.listGroups(ctx.gateway(), agent);
}

/** One group and every case in it. */
export async function getGroup(ctx: Context, id: string): Promise<{ group: api.CaseGroup; cases: api.EvalCase[] }> {
  const sent = await api.getGroup(ctx.gateway(), id);
  return { group: sent.group, cases: sent.cases.map(whole) };
}

/** The group diagnosed on the judge model: the cause its calls share and the smallest fix (one eval). */
export async function proposeFix(ctx: Context, id: string): Promise<api.CaseGroup> {
  return api.proposeGroup(ctx.gateway(), id);
}

/** A proposed setting written as a new version of the key's corner. */
export async function applyFix(ctx: Context, id: string): Promise<Record<string, unknown>> {
  return api.applyGroup(ctx.gateway(), id);
}

/** A caller like the group's, kept as the agent's own persona (one eval). */
export async function personaOfGroup(ctx: Context, id: string): Promise<api.GeneratedPersonas> {
  return api.personaOfGroup(ctx.gateway(), id);
}

/** The group decided whole, every case waiting in it. */
export async function decideGroup(ctx: Context, id: string, approve: boolean, input: { judgeWasWrong?: boolean | undefined; note?: string | undefined } = {}): Promise<api.CaseGroup> {
  return api.patchGroup(ctx.gateway(), id, {
    status: approve ? "approved" : "dismissed",
    ...(input.judgeWasWrong === true ? { judge_was_wrong: true } : {}),
    ...(input.note === undefined ? {} : { note: input.note }),
  });
}

async function decide(ctx: Context, agent: string, name: string, decision: api.CaseDecision): Promise<api.EvalCase> {
  const found = await getCase(ctx, agent, name);
  return whole(await api.patchCase(ctx.gateway(), found.id, decision));
}

// The defaults the gateway leaves out, written in: every front reads one shape.
function whole(sent: api.SentCase): api.EvalCase {
  return {
    ...sent,
    status: sent.status ?? "approved",
    broke: sent.broke ?? [],
    source_version: sent.source_version ?? null,
    kept_in_repo: sent.kept_in_repo ?? false,
    decided_by: sent.decided_by ?? null,
  };
}
