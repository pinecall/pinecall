/** The knowledge endpoints: the bases, a contact's memory, the recall and extraction goldens, and the settings an attachment lives in. */

import type {
  ContactMemory,
  ExtractionGolden,
  ExtractionRun,
  Forgotten,
  KnowledgeFile,
  KnowledgeList,
  KnowledgePushed,
  KnowledgeScore,
  KnowledgeUses,
  MemoryScore,
} from "@pinecall/agents/wire";

import { seg, type GatewayClient } from "./client.js";

export type {
  ContactFact,
  ContactMemory,
  DocsConfig,
  ExtractionGolden,
  ExtractionRun,
  Forgotten,
  KnowledgeFile,
  KnowledgeList,
  KnowledgePushed,
  KnowledgeScore,
  KnowledgeUses,
  MemoryScore,
  TuningAnswer,
  TuningBody,
  TuningRow,
} from "@pinecall/agents/wire";

export function listBases(gw: GatewayClient): Promise<KnowledgeList> {
  return gw.get<KnowledgeList>("/v1/knowledge");
}

/** The base is replaced whole, never merged; `language` left out is counted from the files' words. */
export function pushBase(gw: GatewayClient, base: string, files: KnowledgeFile[], language: string | undefined): Promise<KnowledgePushed> {
  return gw.put<KnowledgePushed>(`/v1/knowledge/${seg(base)}`, { files, ...(language === undefined ? {} : { language }) });
}

export async function deleteBase(gw: GatewayClient, base: string): Promise<void> {
  await gw.delete(`/v1/knowledge/${seg(base)}`);
}

/** recall@k and nDCG@10 of a golden's questions against a base; `k` left out is the gateway's default. */
export function scoreBase(gw: GatewayClient, base: string, questions: unknown[], k: number | undefined): Promise<KnowledgeScore> {
  return gw.post<KnowledgeScore>(`/v1/knowledge/${seg(base)}/eval`, { questions, ...(k === undefined ? {} : { k }) });
}

export function listAttached(gw: GatewayClient): Promise<KnowledgeUses> {
  return gw.get<KnowledgeUses>("/v1/knowledge/attached");
}

export function getContactMemory(gw: GatewayClient, contact: string): Promise<ContactMemory> {
  return gw.get<ContactMemory>(`/v1/contacts/${seg(contact)}/memory`);
}

export function deleteContactMemory(gw: GatewayClient, contact: string): Promise<Forgotten> {
  return gw.delete<Forgotten>(`/v1/contacts/${seg(contact)}/memory`);
}

/** Takes the whole golden: each question carries its own facts, so no contact is involved. */
export function scoreMemory(gw: GatewayClient, questions: unknown[], k: number | undefined): Promise<MemoryScore> {
  return gw.post<MemoryScore>("/v1/contacts/memory/eval", { questions, ...(k === undefined ? {} : { k }) });
}

/** One extraction per case, run by the gateway against whoever holds the agent. */
export function runExtraction(gw: GatewayClient, agent: string, cases: ExtractionGolden[]): Promise<ExtractionRun> {
  return gw.post<ExtractionRun>(`/v1/agents/${seg(agent)}/memory/extraction`, { cases });
}
