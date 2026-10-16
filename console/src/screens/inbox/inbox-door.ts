/** Inbox doors: per-contact threads and writing to a closed thread. Optional on older gateways. */

import { z } from "zod";

import { GatewayError, post, read, type Credentials } from "@pinecall/core/api";

// GET /v1/agents/{slug}/threads: contact name and unread count. Loose so new fields don't fail parsing.
const DoorThreadSchema = z.looseObject({
  contact: z.string(),
  name: z.string().nullish(),
  unread: z.number().nullish(),
});
const DoorThreadsSchema = z.looseObject({ threads: z.array(DoorThreadSchema) });
export type DoorThread = z.infer<typeof DoorThreadSchema>;

/** Threads by contact, or null when the gateway lacks the door (404). */
export async function readDoorThreads(credentials: Credentials, agent: string): Promise<Map<string, DoorThread> | null> {
  try {
    const answered = DoorThreadsSchema.parse(await read(credentials, `/v1/agents/${encodeURIComponent(agent)}/threads`));
    return new Map(answered.threads.map((one) => [one.contact, one]));
  } catch (refused) {
    if (refused instanceof GatewayError && (refused.status === 404 || refused.status === 405)) return null;
    throw refused;
  }
}

/** Mark the thread read for this reader. */
export async function markRead(credentials: Credentials, agent: string, contact: string): Promise<void> {
  await post(credentials, `/v1/agents/${encodeURIComponent(agent)}/threads/${encodeURIComponent(contact)}/read`, {});
}

/** Write to a closed thread as the agent, within the channel's window. */
export async function writeTo(credentials: Credentials, agent: string, contact: string, text: string): Promise<void> {
  await post(credentials, `/v1/agents/${encodeURIComponent(agent)}/threads/${encodeURIComponent(contact)}/messages`, { text });
}
