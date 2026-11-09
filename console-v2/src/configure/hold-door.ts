/** The hold melody's doors: what plays while a tool runs, a file of the org's, silence, and how long it waits. */

import { z } from "zod";

import { answered, doorUrl, headersFor, put, read, type Credentials } from "@pinecall/core/api";

const HoldSchema = z.looseObject({ played: z.enum(["default", "off", "custom"]), name: z.string().nullish(), seconds: z.number().nullish(), after_s: z.number().default(2.5), fixed: z.boolean().default(false) });
export type Hold = z.infer<typeof HoldSchema>;

const holdDoor = (agent: string): string => `/v1/agents/${encodeURIComponent(agent)}/pipeline/hold-audio`;

export async function readHold(credentials: Credentials, agent: string): Promise<Hold> {
  return HoldSchema.parse(await read(credentials, holdDoor(agent)));
}

/** The runtime's melody back, or silence; an uploaded clip is forgotten either way. */
export async function chooseHold(credentials: Credentials, agent: string, played: "default" | "off"): Promise<Hold> {
  return HoldSchema.parse(await put(credentials, `${holdDoor(agent)}/played`, { played }));
}

export async function setHoldAfter(credentials: Credentials, agent: string, after_s: number): Promise<void> {
  await put(credentials, `${holdDoor(agent)}/after`, { after_s });
}

// Raw bytes as the body, no multipart: the gateway decodes whatever it is given.
export async function uploadHold(credentials: Credentials, agent: string, file: File): Promise<Hold> {
  const answer = await fetch(doorUrl(credentials, holdDoor(agent), { name: file.name }), { method: "PUT", headers: { ...headersFor(credentials), "content-type": file.type || "application/octet-stream" }, body: file });
  return HoldSchema.parse(await answered(answer));
}

// An <audio> cannot send a key and keys never go in addresses, so it plays a blob. The caller revokes it.
export async function holdBlob(credentials: Credentials, agent: string): Promise<string> {
  const answer = await fetch(doorUrl(credentials, `${holdDoor(agent)}/audio`), { headers: headersFor(credentials) });
  if (!answer.ok) await answered(answer);
  return URL.createObjectURL(await answer.blob());
}
