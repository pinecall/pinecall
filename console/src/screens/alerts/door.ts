/** The webhook doors: where the org's alerts are posted, set with its secret, read back signed or not, dropped, and proven once. */

import { z } from "zod";

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";

// runtime wire/rest/webhooks.py: WebhookResponse; null when the org posts its alerts nowhere.
const WebhookSchema = z.object({ url: z.string(), signed: z.boolean() });
const TestedSchema = z.object({ sent: z.boolean(), error: z.string().nullable() });

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
