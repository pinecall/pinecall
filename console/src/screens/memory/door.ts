/** Memory doors: read and forget contacts at the gateway, run the memory goldens locally. */

import { type ContactMemory, ContactMemorySchema, type ExtractionRun, ExtractionRunSchema, type Forgotten, ForgottenSchema, type MemoryScore, MemoryScoreSchema } from "@pinecall/core/wire/rest-retrieval";
import { z } from "zod";

import { GatewayError, drop, read, type Credentials } from "@pinecall/core/api";
import { dev } from "../../lib/dev";

/** The directory's recall golden and extraction cases. */
const HereSchema = z.object({
  agent: z.string().nullable(),
  golden: z.string().nullable(),
  questions: z.int(),
  cases: z.array(z.string()),
});
export type Here = z.infer<typeof HereSchema>;

/** All facts kept about one contact, current first. */
export async function readContact(credentials: Credentials, contact: string): Promise<ContactMemory> {
  return ContactMemorySchema.parse(await read(credentials, `/v1/contacts/${encodeURIComponent(contact)}/memory`));
}

/** Delete every fact about a contact (right to be forgotten); returns the count. */
export async function forgetContact(credentials: Credentials, contact: string): Promise<Forgotten> {
  return ForgottenSchema.parse(await drop(credentials, `/v1/contacts/${encodeURIComponent(contact)}/memory`));
}

/** The goldens in the agent's directory, read by its `pinecall start` process. */
export async function readHere(credentials: Credentials, agent: string): Promise<Here> {
  return HereSchema.parse(await dev(credentials, agent, "memory.roster", { agent }));
}

/** Run the recall golden, scored by code without a model. */
export async function askRecall(credentials: Credentials, agent: string): Promise<MemoryScore> {
  return MemoryScoreSchema.parse(await dev(credentials, agent, "memory.eval", { agent }));
}

/** Run the extraction goldens: one model call per case, judged by code. */
export async function runExtraction(credentials: Credentials, agent: string): Promise<ExtractionRun> {
  return ExtractionRunSchema.parse(await dev(credentials, agent, "memory.extraction", { agent }));
}

// GET /v1/agents/{slug}/memory, newest first. Older gateways 404; the screen then reads per contact.
const AgentFactSchema = z.object({
  id: z.string(),
  contact: z.string(),
  text: z.string(),
  category: z.string().nullish(),
  written_at: z.number(),
});
export type AgentFact = z.infer<typeof AgentFactSchema>;

const AgentMemorySchema = z.object({ facts: z.array(AgentFactSchema), next: z.union([z.string(), z.number()]).nullish() });

/** Every caller's current facts, or null when the gateway lacks the door. */
export async function readAgentMemory(credentials: Credentials, agent: string): Promise<AgentFact[] | null> {
  try {
    return AgentMemorySchema.parse(await read(credentials, `/v1/agents/${encodeURIComponent(agent)}/memory`)).facts;
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === 404) return null;
    throw failed;
  }
}

/** Delete a single fact. */
export async function dropFact(credentials: Credentials, id: string): Promise<void> {
  await drop(credentials, `/v1/memory/facts/${encodeURIComponent(id)}`);
}
