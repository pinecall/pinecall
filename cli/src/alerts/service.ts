/** Alerts: the monitors the org watches, where its alerts are posted, and where its traces go. */

import { z } from "zod";

import * as api from "../api/alerts.js";
import type { Context } from "../context.js";
import { PinecallError, UsageError } from "../errors.js";

export { METRICS, type Collector, type Metric, type Monitor, type Webhook, type WebhookTest } from "../api/alerts.js";

/** What `monitors add` takes: a number, the line and its side, the window, the agent or every one. */
export const AddMonitorInput = z.object({
  name: z.string().min(1),
  metric: z.enum(api.METRICS, { error: `--metric names one of ${api.METRICS.join(", ")}` }),
  /** True fires when the number is over the line, false when it is under (a held_rate floor). */
  above: z.boolean(),
  threshold: z.number().finite(),
  windowDays: z.union([z.literal(1), z.literal(7), z.literal(30)], { error: "--days takes 1, 7 or 30" }).default(7),
  agent: z.string().min(1).optional(),
});
export type AddMonitorInput = z.infer<typeof AddMonitorInput>;

/** What `webhook set` takes: the URL, and the secret read off stdin, never a flag. */
export const SetWebhookInput = z.object({
  url: z.url({ error: "a webhook is an http(s) URL alerts are posted to, like https://hooks.example.com/pinecall" }),
  secret: z.string().min(1).nullable().default(null),
});
export type SetWebhookInput = z.infer<typeof SetWebhookInput>;

/** What `telemetry set` takes: the collector, each header's value read off stdin, and whether words travel. */
export const SetCollectorInput = z.object({
  endpoint: z.url({ error: "a collector is an http(s) URL an OTLP exporter posts to, like https://otlp.example.com/v1/traces" }),
  headers: z.record(z.string().min(1), z.string().min(1)).default({}),
  pii: z.boolean().default(false),
});
export type SetCollectorInput = z.infer<typeof SetCollectorInput>;

export async function listMonitors(ctx: Context): Promise<api.Monitor[]> {
  return api.listMonitors(ctx.gateway());
}

export async function addMonitor(ctx: Context, input: AddMonitorInput): Promise<api.Monitor> {
  return api.createMonitor(ctx.gateway(), {
    name: input.name,
    metric: input.metric,
    above: input.above,
    threshold: input.threshold,
    window_days: input.windowDays,
    ...(input.agent === undefined ? {} : { agent: input.agent }),
  });
}

export async function removeMonitor(ctx: Context, id: string): Promise<{ id: string }> {
  if (!id.startsWith("mon_")) throw new UsageError(`a monitor's id starts with mon_, as \`pinecall monitors\` lists them; not ${id}`);
  await api.deleteMonitor(ctx.gateway(), id);
  return { id };
}

export async function getWebhook(ctx: Context): Promise<api.Webhook | null> {
  return api.getWebhook(ctx.gateway());
}

export async function setWebhook(ctx: Context, input: SetWebhookInput): Promise<api.Webhook> {
  await api.setWebhook(ctx.gateway(), input.url, input.secret);
  return { url: input.url, signed: input.secret !== null };
}

/** One signed `webhook.test` post, waited for; a URL that did not take it is a failed check. */
export async function testWebhook(ctx: Context): Promise<api.WebhookTest> {
  const tested = await api.testWebhook(ctx.gateway());
  if (!tested.sent) throw new PinecallError(`the URL did not take it: ${tested.error ?? "no answer"}`);
  return tested;
}

export async function clearWebhook(ctx: Context): Promise<{ cleared: true }> {
  await api.deleteWebhook(ctx.gateway());
  return { cleared: true };
}

export async function getCollector(ctx: Context): Promise<api.Collector | null> {
  return api.getCollector(ctx.gateway());
}

export async function setCollector(ctx: Context, input: SetCollectorInput): Promise<api.Collector> {
  await api.setCollector(ctx.gateway(), input.endpoint, input.headers, input.pii);
  return { endpoint: input.endpoint, header_names: Object.keys(input.headers), pii: input.pii };
}

export async function clearCollector(ctx: Context): Promise<{ cleared: true }> {
  await api.deleteCollector(ctx.gateway());
  return { cleared: true };
}
