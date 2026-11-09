/** Advanced's own doors, beside the settings Configure already reads: what the organization sets for all its agents. */

import { z } from "zod";

import { read, type Credentials } from "@pinecall/core/api";

const WebhookSchema = z.looseObject({ url: z.string(), signed: z.boolean() }).nullable();
const PolicySchema = z.looseObject({
  policy: z.looseObject({
    retention_days: z.number().nullish(),
    calling_hours: z.looseObject({ from: z.number(), until: z.number() }).nullish(),
    consent_everywhere: z.boolean().default(false),
    recording_notice: z.boolean().default(true),
  }),
});

export type Webhook = z.infer<typeof WebhookSchema>;
export type Policy = z.infer<typeof PolicySchema>["policy"];

export async function readWebhook(credentials: Credentials): Promise<Webhook> {
  return WebhookSchema.parse(await read(credentials, "/v1/webhook"));
}

export async function readPolicy(credentials: Credentials): Promise<Policy> {
  return PolicySchema.parse(await read(credentials, "/v1/org/policy")).policy;
}
