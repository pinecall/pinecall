/** The knowledge endpoints: the bases, a contact's memory, the recall and extraction goldens, and the settings an attachment lives in. */

import type {
  ContactMemory,
  ExtractionGolden,
  ExtractionRun,
  Forgotten,
  KnowledgeFile,
  KnowledgeList,
  KnowledgePushed as PushedOnTheWire,
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
  KnowledgeScore,
  KnowledgeUses,
  MemoryScore,
  TuningAnswer,
  TuningBody,
  TuningRow,
} from "@pinecall/agents/wire";

/** `PUT /v1/knowledge/{base}`, the answer: the wire's, plus `kept`, the files of the base the push did not touch (an intersection, so the wire may make it required). */
export type KnowledgePushed = PushedOnTheWire & { kept?: number };

/** One file of a base as `GET /v1/knowledge/{base}` lists it: its path, its size, its chunks, when it was pushed; never its text. */
export interface KnowledgeFileRow {
  path: string;
  chars: number;
  chunks: number;
  pushed_at: number;
}

/** `GET /v1/knowledge/{base}`: the base's files. `kept` is false for a base whose files were never stored, only its chunks. */
export interface KnowledgeFiles {
  base: string;
  kept: boolean;
  files: KnowledgeFileRow[];
}

/** `GET /v1/knowledge/{base}/files/{path}`: one file, text and all. */
export interface KnowledgeFileRead {
  path: string;
  text: string;
  chunks: number;
  pushed_at: number;
}

export function listBases(gw: GatewayClient): Promise<KnowledgeList> {
  return gw.get<KnowledgeList>("/v1/knowledge");
}

/**
 * The files written into the base by path and the rest kept; with `replace`, the base becomes the
 * folder. `language` left out is counted from the files' words.
 */
export function pushBase(gw: GatewayClient, base: string, files: KnowledgeFile[], language: string | undefined, replace = false): Promise<KnowledgePushed> {
  const body = { files, ...(language === undefined ? {} : { language }) };
  return gw.request<KnowledgePushed>(`/v1/knowledge/${seg(base)}`, { method: "PUT", body, ...(replace ? { query: { replace: true } } : {}) });
}

export function listFiles(gw: GatewayClient, base: string): Promise<KnowledgeFiles> {
  return gw.get<KnowledgeFiles>(`/v1/knowledge/${seg(base)}`);
}

export function getFile(gw: GatewayClient, base: string, path: string): Promise<KnowledgeFileRead> {
  return gw.get<KnowledgeFileRead>(fileOf(base, path));
}

/** One file and its chunks out of the base; the base goes with its last file. */
export async function deleteFile(gw: GatewayClient, base: string, path: string): Promise<void> {
  await gw.delete(fileOf(base, path));
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

// A file's path keeps its slashes: each segment is escaped on its own.
function fileOf(base: string, path: string): string {
  return `/v1/knowledge/${seg(base)}/files/${path.split("/").map(seg).join("/")}`;
}
