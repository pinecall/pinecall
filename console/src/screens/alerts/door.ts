/** The alerts doors: the org's alerts kept, and the webhook they are posted to, set, read back, dropped and proven once. */

import { z } from "zod";

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";

// runtime wire/rest/webhooks.py: WebhookResponse; null when the org posts its alerts nowhere.
const WebhookSchema = z.object({ url: z.string(), signed: z.boolean() });
const TestedSchema = z.object({ sent: z.boolean(), error: z.string().nullable() });
// runtime alerts/schemas.py: AlertRow, newest first.
const AlertSchema = z.object({
  id: z.string(),
  org: z.string(),
  env: z.enum(["production", "sandbox"]),
  agent: z.string().nullable(),
  kind: z.string(),
  data: z.record(z.string(), z.unknown()),
  mailed: z.boolean(),
  at: z.string(),
});
const AlertListSchema = z.object({ alerts: z.array(AlertSchema) });

/** One alert kept: whose, what kind, its data, whether it was mailed, when. */
export type Alert = z.infer<typeof AlertSchema>;

/** The org's webhook as the gateway says it: the URL, and whether posts are signed; never the secret. */
export type Webhook = z.infer<typeof WebhookSchema>;
export type Tested = z.infer<typeof TestedSchema>;

const DOOR = "/v1/webhook";

export async function readWebhook(credentials: Credentials): Promise<Webhook | null> {
  const answered: unknown = await read(credentials, DOOR);
  return answered === null ? null : WebhookSchema.parse(answered);
}

/** Set the webhook, replacing the one the org had; the secret is sent once and never read back. */
export async function putWebhook(credentials: Credentials, url: string, secret: string | null): Promise<void> {
  await put(credentials, DOOR, { url, secret });
}

export async function dropWebhook(credentials: Credentials): Promise<void> {
  await drop(credentials, DOOR);
}

/** One signed test post, waited for: whether the URL answered 2xx, and what went wrong if not. */
export async function testWebhook(credentials: Credentials): Promise<Tested> {
  return TestedSchema.parse(await post(credentials, `${DOOR}/test`, {}));
}

/** The org's alerts in this console's world, newest first. */
export async function readAlerts(credentials: Credentials): Promise<Alert[]> {
  return AlertListSchema.parse(await read(credentials, "/v1/alerts")).alerts;
}
