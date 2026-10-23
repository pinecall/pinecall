/** The alerts endpoints: monitors, the org's webhook, its telemetry collector. */

import { seg, type GatewayClient } from "./client.js";

/** The numbers a monitor can watch, as the gateway names them. */
export const METRICS = ["e2e_median_s", "llm_median_s", "held_rate", "escalated_rate", "tool_failure_rate", "spend_usd", "calls"] as const;
export type Metric = (typeof METRICS)[number];

/** One monitor as the gateway lists it. */
export interface Monitor {
  id: string;
  name: string;
  metric: Metric;
  above: boolean;
  threshold: number;
  window_days: number;
  agent: string | null;
  created_by: string;
  fired_on: string | null;
  fired_value: number | null;
}

/** `POST /v1/monitors`. */
export interface NewMonitor {
  name: string;
  metric: Metric;
  above: boolean;
  threshold: number;
  window_days: number;
  agent?: string;
}

/** Where the org's alerts are posted, as the gateway reads it back: never the secret. */
export interface Webhook {
  url: string;
  signed: boolean;
}

/** One alert the gateway kept: whose, what kind, its data, whether it was mailed, when. */
export interface Alert {
  id: string;
  org: string;
  env: "production" | "sandbox";
  agent: string | null;
  kind: string;
  data: Record<string, unknown>;
  mailed: boolean;
  at: string;
}

/** `POST /v1/webhook/test`: whether the URL answered 2xx. */
export interface WebhookTest {
  sent: boolean;
  error: string | null;
}

/** Where the org's traces go, as the gateway reads it back: the headers' names, never their values. */
export interface Collector {
  endpoint: string;
  header_names: string[];
  pii: boolean;
}

export async function listMonitors(gw: GatewayClient): Promise<Monitor[]> {
  return (await gw.get<{ monitors: Monitor[] }>("/v1/monitors")).monitors;
}

export function createMonitor(gw: GatewayClient, body: NewMonitor): Promise<Monitor> {
  return gw.post<Monitor>("/v1/monitors", body);
}

export async function deleteMonitor(gw: GatewayClient, id: string): Promise<void> {
  await gw.delete(`/v1/monitors/${seg(id)}`);
}

export function getWebhook(gw: GatewayClient): Promise<Webhook | null> {
  return gw.get<Webhook | null>("/v1/webhook");
}

export async function setWebhook(gw: GatewayClient, url: string, secret: string | null): Promise<void> {
  await gw.put("/v1/webhook", { url, secret });
}

export function testWebhook(gw: GatewayClient): Promise<WebhookTest> {
  return gw.post<WebhookTest>("/v1/webhook/test", {});
}

export async function deleteWebhook(gw: GatewayClient): Promise<void> {
  await gw.delete("/v1/webhook");
}

export function getCollector(gw: GatewayClient): Promise<Collector | null> {
  return gw.get<Collector | null>("/v1/telemetry");
}

export async function setCollector(gw: GatewayClient, endpoint: string, headers: Record<string, string>, pii: boolean): Promise<void> {
  await gw.put("/v1/telemetry", { endpoint, headers, pii });
}

export async function deleteCollector(gw: GatewayClient): Promise<void> {
  await gw.delete("/v1/telemetry");
}

/** `GET /v1/alerts`: the org's alerts in the key's env, newest first. */
export async function listAlerts(gw: GatewayClient, limit: number): Promise<Alert[]> {
  return (await gw.get<{ alerts: Alert[] }>(`/v1/alerts?limit=${limit}`)).alerts;
}
