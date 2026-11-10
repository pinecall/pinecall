/** Knowledge's doors: the org's bases and who searches them, a base's files one at a time, and the facts its agents kept. */

import { z } from "zod";

import { drop, GatewayError, put, read, type Credentials } from "@pinecall/core/api";
import { type KnowledgeBase, type KnowledgeFilePushed, KnowledgeFilePushedSchema, type KnowledgeFileRead, KnowledgeFileReadSchema, type KnowledgeFiles, KnowledgeFilesSchema, KnowledgeListSchema, KnowledgeUsesSchema } from "@pinecall/core/wire/rest-retrieval";
import { count } from "../lib/format";

export const A_DOCUMENT = /\.(md|markdown|txt)$/i;

/** `1 chunk`, `1,204 chunks`. */
export function chunksIn(chunks: number): string {
  return `${count(chunks)} ${chunks === 1 ? "chunk" : "chunks"}`;
}

/** A base and the agents that search it. */
export interface BaseRead extends KnowledgeBase {
  agents: string[];
}

export async function readBases(credentials: Credentials): Promise<BaseRead[]> {
  const [listed, uses] = await Promise.all([KnowledgeListSchema.parse(await read(credentials, "/v1/knowledge")), KnowledgeUsesSchema.parse(await read(credentials, "/v1/knowledge/attached"))]);
  const readers = new Map(uses.bases.map((one) => [one.base, one.agents]));
  return listed.bases.map((base) => ({ ...base, agents: readers.get(base.base) ?? [] }));
}

const baseDoor = (base: string): string => `/v1/knowledge/${encodeURIComponent(base)}`;

// Each segment on its own: a file's path keeps its slashes.
const fileDoor = (base: string, path: string): string => `${baseDoor(base)}/files/${path.split("/").map(encodeURIComponent).join("/")}`;

export async function readFiles(credentials: Credentials, base: string): Promise<KnowledgeFiles> {
  return KnowledgeFilesSchema.parse(await read(credentials, baseDoor(base)));
}

export async function readFile(credentials: Credentials, base: string, path: string): Promise<KnowledgeFileRead> {
  return KnowledgeFileReadSchema.parse(await read(credentials, fileDoor(base, path)));
}

/** A file put by its path, begun or written over; only it is cut again. */
export async function putFile(credentials: Credentials, base: string, path: string, text: string): Promise<KnowledgeFilePushed> {
  return KnowledgeFilePushedSchema.parse(await put(credentials, fileDoor(base, path), { text }));
}

/** A file and its chunks taken out; the base goes with its last file. */
export async function dropFile(credentials: Credentials, base: string, path: string): Promise<void> {
  await drop(credentials, fileDoor(base, path));
}

export async function dropBase(credentials: Credentials, base: string): Promise<void> {
  await drop(credentials, baseDoor(base));
}

const FactSchema = z.object({ id: z.string(), agent: z.string(), contact: z.string(), text: z.string(), category: z.string().nullish(), written_at: z.number() });
const FactsSchema = z.object({ facts: z.array(FactSchema), next: z.string().nullish() });

export type Fact = z.infer<typeof FactSchema>;
export type Facts = z.infer<typeof FactsSchema>;

/** One page of what the org's agents remember, or null when this gateway keeps no memory: that is not an empty list. */
export async function readFacts(credentials: Credentials, words: string, after: string | null): Promise<Facts | null> {
  const params: Record<string, string> = {};
  if (words !== "") params["q"] = words;
  if (after !== null) params["after"] = after;
  try {
    return FactsSchema.parse(await read(credentials, "/v1/memory", params));
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === 404) return null;
    throw failed;
  }
}

export async function forgetFact(credentials: Credentials, id: string): Promise<void> {
  await drop(credentials, `/v1/memory/facts/${encodeURIComponent(id)}`);
}
