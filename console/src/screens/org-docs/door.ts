/** Org Docs doors: bases in this world with their reader agents, and per-file read/write. */

import { type KnowledgeBase, type KnowledgeFilePushed, KnowledgeFilePushedSchema, type KnowledgeFileRead, KnowledgeFileReadSchema, type KnowledgeFiles, KnowledgeFilesSchema, KnowledgeListSchema, KnowledgeUsesSchema } from "@pinecall/core/wire/rest-retrieval";

import { drop, put, read, type Credentials } from "@pinecall/core/api";

/** A base plus the agents that read it. */
export interface BaseRead extends KnowledgeBase {
  agents: string[];
}

/** Every base in this world, with its reader agents. */
export async function readBasesRead(credentials: Credentials): Promise<BaseRead[]> {
  const [listed, uses] = await Promise.all([
    KnowledgeListSchema.parse(await read(credentials, "/v1/knowledge")),
    KnowledgeUsesSchema.parse(await read(credentials, "/v1/knowledge/attached")),
  ]);
  const readers = new Map(uses.bases.map((one) => [one.base, one.agents]));
  return listed.bases.map((base) => ({ ...base, agents: readers.get(base.base) ?? [] }));
}

// Encode each path segment, keeping slashes.
function fileDoor(base: string, path: string): string {
  return `/v1/knowledge/${encodeURIComponent(base)}/files/${path.split("/").map(encodeURIComponent).join("/")}`;
}

/** List a base's files with size and chunking status. */
export async function readFiles(credentials: Credentials, base: string): Promise<KnowledgeFiles> {
  return KnowledgeFilesSchema.parse(await read(credentials, `/v1/knowledge/${encodeURIComponent(base)}`));
}

export async function readFile(credentials: Credentials, base: string, path: string): Promise<KnowledgeFileRead> {
  return KnowledgeFileReadSchema.parse(await read(credentials, fileDoor(base, path)));
}

/** Create or replace a file; only that file is re-chunked. */
export async function putFile(credentials: Credentials, base: string, path: string, text: string): Promise<KnowledgeFilePushed> {
  return KnowledgeFilePushedSchema.parse(await put(credentials, fileDoor(base, path), { text }));
}

/** Delete a file and its chunks; deleting the last file deletes the base. */
export async function dropFile(credentials: Credentials, base: string, path: string): Promise<void> {
  await drop(credentials, fileDoor(base, path));
}
