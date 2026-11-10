/** The monitors' doors: the numbers watched in this environment, one more watched or let go, the alerts kept, and the webhook they are posted to. */

import { z } from "zod";

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";
import { type Monitor, MonitorListSchema, type MonitorMetric, type MonitorPut, MonitorSchema } from "@pinecall/core/wire/rest-evals";

export type { Monitor, MonitorMetric, MonitorPut };

export async function readMonitors(credentials: Credentials): Promise<Monitor[]> {
  return MonitorListSchema.parse(await read(credentials, "/v1/monitors")).monitors;
}

/** Watch a number: it fires, once a day, when it crosses the line over its window. */
export async function addMonitor(credentials: Credentials, wanted: MonitorPut): Promise<Monitor> {
  return MonitorSchema.parse(await post(credentials, "/v1/monitors", wanted));
}

/** Stop watching; one an app's code declares is refused, naming the app. */
export async function dropMonitor(credentials: Credentials, id: string): Promise<void> {
  await drop(credentials, `/v1/monitors/${encodeURIComponent(id)}`);
}

const AlertSchema = z.looseObject({
  id: z.string(),
  /** The agent whose calls it is about; none for what is the whole org's. */
  agent: z.string().nullable(),
  kind: z.string(),
  data: z.record(z.string(), z.unknown()),
  /** Whether the org's admins were mailed it. */
  mailed: z.boolean(),
  at: z.string(),
});
export type Alert = z.infer<typeof AlertSchema>;

// The door's own most: alerts are kept ninety days.
const AS_MANY_AS_IT_GIVES = 200;

/** The org's alerts in this environment, newest first. */
export async function readAlerts(credentials: Credentials): Promise<Alert[]> {
  return z.looseObject({ alerts: z.array(AlertSchema) }).parse(await read(credentials, "/v1/alerts", { limit: AS_MANY_AS_IT_GIVES })).alerts;
}

const WebhookSchema = z.looseObject({ url: z.string(), signed: z.boolean() });
export type Webhook = z.infer<typeof WebhookSchema>;

/** Where the org's alerts are posted, never its secret; null when nowhere. */
export async function readWebhook(credentials: Credentials): Promise<Webhook | null> {
  const answered = await read(credentials, "/v1/webhook");
  return answered === null ? null : WebhookSchema.parse(answered);
}

/** Keep the webhook, over the one there was; the secret every post is signed with is sent once and never read back. */
export async function putWebhook(credentials: Credentials, url: string, secret: string | null): Promise<void> {
  await put(credentials, "/v1/webhook", { url, secret });
}

export async function dropWebhook(credentials: Credentials): Promise<void> {
  await drop(credentials, "/v1/webhook");
}

/** One test post, signed as every alert is and waited for: whether a 2xx came back, else why not. */
export async function testWebhook(credentials: Credentials): Promise<{ sent: boolean; error: string | null }> {
  return z.looseObject({ sent: z.boolean(), error: z.string().nullable() }).parse(await post(credentials, "/v1/webhook/test", {}));
}
