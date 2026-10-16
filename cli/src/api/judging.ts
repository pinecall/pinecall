/** The judging endpoints: the judges of the org or of one agent, one tried on calls, and whether the org's calls are judged. */

import type { JudgeList, JudgeRequest, JudgeTried, JudgeTry, ModelConfig } from "@pinecall/agents/wire";

import { seg, type GatewayClient } from "./client.js";

export type { JudgeList, JudgeRequest, JudgeRow, JudgeTried, JudgeTry, Judgment, ModelConfig } from "@pinecall/agents/wire";

/** Whose judges: the org's (null), or one agent's by its slug. */
export type JudgeOwner = string | null;

/** `GET` and `PUT /v1/org/judging`, as the gateway answers them. */
export interface Judging {
  on: boolean;
  /** What the platform spends on one call's judges at most, on its own model; null when unbounded. */
  ceiling_usd: number | null;
  /** The org's own judge model; null or absent on Pinecall's. */
  model?: ModelConfig | null;
}

/** `PUT /v1/org/judging`: the whole, since what is not sent is not kept. */
export interface JudgingRequest {
  on: boolean;
  model?: ModelConfig;
}

export function listJudges(gw: GatewayClient, owner: JudgeOwner): Promise<JudgeList> {
  return gw.get<JudgeList>(judgesPath(owner));
}

/** A judge of one's own written whole, or one of Pinecall's switched with `on` alone; answers the list after. */
export function putJudge(gw: GatewayClient, owner: JudgeOwner, name: string, body: JudgeRequest): Promise<JudgeList> {
  return gw.put<JudgeList>(`${judgesPath(owner)}/${seg(name)}`, body);
}

export function deleteJudge(gw: GatewayClient, owner: JudgeOwner, name: string): Promise<JudgeList> {
  return gw.delete<JudgeList>(`${judgesPath(owner)}/${seg(name)}`);
}

/** One judge asked of finished calls; nothing is written. Always an agent's. */
export function tryJudge(gw: GatewayClient, agent: string, body: JudgeTry): Promise<JudgeTried> {
  return gw.post<JudgeTried>(`${judgesPath(agent)}/try`, body);
}

export function getJudging(gw: GatewayClient): Promise<Judging> {
  return gw.get<Judging>("/v1/org/judging");
}

export function setJudging(gw: GatewayClient, body: JudgingRequest): Promise<Judging> {
  return gw.put<Judging>("/v1/org/judging", body);
}

function judgesPath(owner: JudgeOwner): string {
  return owner === null ? "/v1/org/judges" : `/v1/agents/${seg(owner)}/judges`;
}
