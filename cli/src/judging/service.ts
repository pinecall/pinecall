/** Judging: every judge a call meets, one tried on calls, and whether the org's calls are judged and on what. */

import { z } from "zod";

import { cornerRead, readSettings } from "../agents/service/corners.js";
import * as api from "../api/judging.js";
import type { Context } from "../context.js";
import { UsageError } from "../errors.js";
import * as providers from "../providers/service.js";

export type { Calibration, JudgeAgreement, JudgeList, JudgeOwner, JudgeRequest, JudgeRow, JudgeTried, JudgeTry, Judging, Judgment, ModelConfig } from "../api/judging.js";

// Mirrors the gateway's name rule so a bad name gets a readable error.
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MOST_CALLS = 50;
const CHOICE = "choice:";
const TRIGGER = "trigger:";

export const READS = ["prompt", "evidence", "facts"] as const;

export const NAME_SHAPE = (name: string): string => `${name} is no name for a judge: lower-case letters and digits joined by hyphens — offers-next-slot`;
export const NO_QUESTION = "a judge needs --asks: the one sentence the judge model answers about the call";
export const ONE_OR_THE_OTHER = "--org and --agent name two lists: the org's judges, or one agent's own";
export const TRY_IS_AN_AGENTS = "try asks one agent's calls: --agent names it, never --org";
export const WHICH_CALLS = "try needs the calls: --last <n> (1 to 50) or --calls <id,id…>, one of them";
const NOT_AN_ANSWER = (said: string): string => `--answer ${said}: verdict (held or broken), score (1 to 5), or choice:a,b,c (two choices at least)`;
const NOT_WHEN = (said: string): string => `--when ${said}: always, simulations, or trigger:'…' (a yes-or-no asked first; a no is N/A)`;
const NOT_READ = (said: string): string => `--reads ${said}: any of ${READS.join(", ")}, comma-separated`;
const ONE_MODEL = "--model names one of yours and --platform Pinecall's: one of them";
const OPTIONS_NEED_A_MODEL = "--option is the plugin's of a model of yours: name it with --model";

/** Whose list a verb acts on: the org's with `org`, else the agent named or the project's only one. */
export const OwnerInput = z.object({
  org: z.boolean().default(false),
  agent: z.string().min(1).optional(),
});
export type OwnerInput = z.infer<typeof OwnerInput>;

/** The flags that write a judge, as typed. */
export const JudgeFlags = z.object({
  asks: z.string().optional(),
  answer: z.string().optional(),
  when: z.string().optional(),
  reads: z.string().optional(),
});
export type JudgeFlags = z.infer<typeof JudgeFlags>;

/** What `judges try` takes: the judge by name (and whole, when not yet saved), and which calls. */
export const TryJudgeInput = JudgeFlags.extend({
  name: z.string().min(1),
  agent: z.string().min(1).optional(),
  last: z.number().int().optional(),
  calls: z.array(z.string().min(1)).optional(),
});
export type TryJudgeInput = z.infer<typeof TryJudgeInput>;

/** What `judging set` takes: on or off, a model of the org's own with its options, or Pinecall's again. */
export const SetJudgingInput = z.object({
  on: z.boolean().optional(),
  model: z.string().min(1).optional(),
  options: z.record(z.string(), z.unknown()).optional(),
  platform: z.boolean().default(false),
  /** An agent whose own judge the answer says beside the org's. */
  agent: z.string().min(1).optional(),
});
export type SetJudgingInput = z.infer<typeof SetJudgingInput>;

/** The org's judging and what it costs: the model, whose key it runs on, whether evals are billed. */
export interface JudgingReport extends api.Judging {
  /** Whether the org brought a key for the model's vendor, so its evals are not billed. */
  own_key: boolean;
  /** The judge the agent named with `--agent` is asked for, over the org's; absent when none was named. */
  agent?: AgentJudging;
}

/** What one agent's calls are judged on: the model its own settings name, the class's own, or the org's. */
export interface AgentJudging {
  agent: string;
  /** `vendor/model` as the agent's settings name it; null when they name none. */
  judge: string | null;
  options: Record<string, unknown>;
  /** The class declares `@judge`: no setting is read for it. */
  declared: boolean;
  /** Whether the org brought a key for that model's vendor, so its evals are not billed. */
  own_key: boolean;
}

/** A list after a change: what was done, and the list as it stands. */
export interface JudgeListChanged extends api.JudgeList {
  done: string;
}

/** The owner of the list: null for the org, else the agent's slug. */
export function ownerOf(ctx: Context, input: OwnerInput): api.JudgeOwner {
  if (input.org && input.agent !== undefined) throw new UsageError(ONE_OR_THE_OTHER);
  return input.org ? null : ctx.slug("judges", { agent: input.agent });
}

/** Why a judge's name is refused, or undefined. */
export function checkJudgeName(name: string): void {
  if (!A_NAME.test(name)) throw new UsageError(NAME_SHAPE(name));
}

/** The body that writes a judge of one's own whole; a flag that does not read is a usage error. */
export function judgeRequestOf(flags: JudgeFlags): api.JudgeRequest {
  const question = flags.asks?.trim() ?? "";
  if (question === "") throw new UsageError(NO_QUESTION);
  return { question, ...answerOf(flags.answer), ...whenOf(flags.when), ...readsOf(flags.reads) };
}

export async function listJudges(ctx: Context, owner: api.JudgeOwner): Promise<api.JudgeList> {
  return api.listJudges(ctx.gateway(), owner);
}

/** Each judge's agreement with the labels people gave: one agent's calls, or every agent's (the org). */
export async function agreement(ctx: Context, owner: api.JudgeOwner): Promise<api.Calibration> {
  return api.getCalibration(ctx.gateway(), owner);
}

export async function addJudge(ctx: Context, owner: api.JudgeOwner, name: string, flags: JudgeFlags): Promise<JudgeListChanged> {
  checkJudgeName(name);
  return { done: `${name} written`, ...(await api.putJudge(ctx.gateway(), owner, name, judgeRequestOf(flags))) };
}

/** One of Pinecall's judges switched for the org or the agent. */
export async function switchJudge(ctx: Context, owner: api.JudgeOwner, name: string, on: boolean): Promise<JudgeListChanged> {
  checkJudgeName(name);
  return { done: `${name} ${on ? "on" : "off"}`, ...(await api.putJudge(ctx.gateway(), owner, name, { on })) };
}

export async function removeJudge(ctx: Context, owner: api.JudgeOwner, name: string): Promise<JudgeListChanged> {
  checkJudgeName(name);
  return { done: `${name} dropped`, ...(await api.deleteJudge(ctx.gateway(), owner, name)) };
}

/** One judge asked of finished calls and nothing written: a written one by its name, or one not yet saved, whole. */
export async function tryJudge(ctx: Context, input: TryJudgeInput): Promise<api.JudgeTried> {
  checkJudgeName(input.name);
  const agent = ctx.slug("judges try", { agent: input.agent });
  if ((input.last === undefined) === (input.calls === undefined)) throw new UsageError(WHICH_CALLS);
  if (input.last !== undefined && (input.last < 1 || input.last > MOST_CALLS)) throw new UsageError(`--last ${input.last} is not 1 to 50 calls`);
  const body: api.JudgeTry = {
    name: input.name,
    ...(input.asks === undefined ? {} : judgeRequestOf(input)),
    ...(input.calls === undefined ? { last: input.last! } : { calls: input.calls }),
  };
  return api.tryJudge(ctx.gateway(), agent, body);
}

export async function getJudging(ctx: Context, agent?: string): Promise<JudgingReport> {
  return withAgent(ctx, await reported(ctx, await api.getJudging(ctx.gateway())), agent);
}

/** Judging on or off, and the model it runs on; the endpoint takes the whole, so what is not changed travels as it stands. */
export async function setJudging(ctx: Context, input: SetJudgingInput): Promise<JudgingReport> {
  const model = modelWanted(input);
  const gw = ctx.gateway();
  const standing = await api.getJudging(gw);
  if (input.on === undefined && model === undefined) return withAgent(ctx, await reported(ctx, standing), input.agent);
  const on = input.on ?? standing.on;
  const kept = model === undefined ? (standing.model ?? null) : model;
  return withAgent(ctx, await reported(ctx, await api.setJudging(gw, kept === null ? { on } : { on, model: kept })), input.agent);
}

/** The model a command line names: one of yours, null for Pinecall's, undefined when it names none. */
function modelWanted(input: SetJudgingInput): api.ModelConfig | null | undefined {
  if (input.platform && input.model !== undefined) throw new UsageError(ONE_MODEL);
  if (input.platform) return null;
  if (input.model === undefined) {
    if (input.options !== undefined) throw new UsageError(OPTIONS_NEED_A_MODEL);
    return undefined;
  }
  const named = providers.parseModelPath(input.model);
  if (named === undefined) throw new UsageError(`--model ${input.model} names no model: vendor/model, or one of ${Object.keys(providers.SHORT_NAMES).join(" · ")}`);
  return input.options === undefined ? named : { ...named, options: input.options };
}

// An agent's own `--judge` wins over the org's: it is read from the settings this key reads, the class's from `fixed`.
async function withAgent(ctx: Context, report: JudgingReport, named: string | undefined): Promise<JudgingReport> {
  if (named === undefined) return report;
  const agent = ctx.slug("judging", { agent: named });
  const answer = await readSettings(ctx, agent);
  const config = cornerRead(answer)?.config;
  const judge = config?.judge ?? null;
  const { vendors } = await providers.listProviderKeys(ctx);
  const vendor = judge === null ? undefined : providers.parseModelPath(judge)?.provider;
  const options = config?.judge_options ?? {};
  return { ...report, agent: { agent, judge, options, declared: answer.fixed.includes("judge"), own_key: vendor !== undefined && vendors.includes(vendor) } };
}

async function reported(ctx: Context, judging: api.Judging): Promise<JudgingReport> {
  const model = judging.model ?? null;
  if (model === null) return { ...judging, own_key: false };
  const { vendors } = await providers.listProviderKeys(ctx);
  return { ...judging, own_key: vendors.includes(model.provider) };
}

function answerOf(said: string | undefined): Pick<api.JudgeRequest, "answer" | "choices"> {
  if (said === undefined || said === "verdict") return { answer: "verdict" };
  if (said === "score") return { answer: "score" };
  if (said.startsWith(CHOICE)) {
    const choices = said.slice(CHOICE.length).split(",").map((one) => one.trim()).filter((one) => one !== "");
    if (choices.length >= 2) return { answer: "choice", choices };
  }
  throw new UsageError(NOT_AN_ANSWER(said));
}

function whenOf(said: string | undefined): Pick<api.JudgeRequest, "when" | "trigger"> {
  if (said === undefined || said === "always") return { when: "always" };
  if (said === "simulations") return { when: "simulations" };
  if (said.startsWith(TRIGGER) && said.slice(TRIGGER.length).trim() !== "") return { when: "trigger", trigger: said.slice(TRIGGER.length).trim() };
  throw new UsageError(NOT_WHEN(said));
}

function readsOf(said: string | undefined): Pick<api.JudgeRequest, "reads"> {
  if (said === undefined) return {};
  const named = said.split(",").map((one) => one.trim()).filter((one) => one !== "");
  const wrong = named.find((one) => !(READS as readonly string[]).includes(one));
  if (wrong !== undefined) throw new UsageError(NOT_READ(wrong));
  return { reads: named as (typeof READS)[number][] };
}
