/** Agents currently connected for the org (GET /v1/agents). */

import { AgentListSchema, type HeldAgent } from "./wire/rest-org.js";

import { read, type Credentials } from "./api";

/** Agents connected in the key's world. A `team` key gets one row per corner. */
export async function readHeldAgents(credentials: Credentials): Promise<HeldAgent[]> {
  return AgentListSchema.parse(await read(credentials, "/v1/agents")).agents;
}
