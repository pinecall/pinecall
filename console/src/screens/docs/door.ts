/** Docs requests: list/drop via the gateway, push/golden via the `pinecall start` process. */

import { type KnowledgeList, KnowledgeListSchema, KnowledgePushedSchema, type KnowledgeScore, KnowledgeScoreSchema } from "@pinecall/core/wire/rest-retrieval";
import { z } from "zod";

import { drop, read, type Credentials } from "@pinecall/core/api";
import { dev } from "../../lib/dev";

/** The local docs folder of the `pinecall start` directory, and its golden if any. */
const HereSchema = z.object({
  agent: z.string().nullable(),
  base: z.string().nullable(),
  directory: z.string().nullable(),
  files: z.int(),
  golden: z.string().nullable(),
  questions: z.int(),
});
export type Here = z.infer<typeof HereSchema>;

/** Push result, with the number of files read from disk. */
const PushedSchema = KnowledgePushedSchema.extend({ files: z.int() });
export type Pushed = z.infer<typeof PushedSchema>;

/** Every base this org has pushed. */
export async function readBases(credentials: Credentials): Promise<KnowledgeList> {
  return KnowledgeListSchema.parse(await read(credentials, "/v1/knowledge"));
}

/** Describe the local docs folder: path, file count, and whether a golden exists. */
export async function readHere(credentials: Credentials, agent: string): Promise<Here> {
  return HereSchema.parse(await dev(credentials, agent, "knowledge.roster", { agent }));
}

/** Push the whole folder; the base is replaced, not merged. */
export async function pushKnowledge(credentials: Credentials, agent: string, base: string): Promise<Pushed> {
  return PushedSchema.parse(await dev(credentials, agent, "knowledge.push", { agent, ...(base === "" ? {} : { base }) }));
}

/** Run the golden against the base: recall@k and nDCG@10. */
export async function askTheGolden(credentials: Credentials, agent: string, base: string): Promise<KnowledgeScore> {
  return KnowledgeScoreSchema.parse(await dev(credentials, agent, "knowledge.eval", { agent, ...(base === "" ? {} : { base }) }));
}

/** Delete a base. Irreversible except by pushing again. */
export async function dropBase(credentials: Credentials, base: string): Promise<void> {
  await drop(credentials, `/v1/knowledge/${encodeURIComponent(base)}`);
}
