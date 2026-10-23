/** Alerts as a terminal reads them: the monitors table, one monitor, the webhook, the collector. */

import { table } from "../kit/table.js";
import type { Alert, Collector, Monitor, Webhook, WebhookTest } from "./service.js";

export const NO_ALERTS = "no alert kept for this org here: none was raised, or none in the last 90 days";
export const NO_MONITORS = "this org watches nothing · `pinecall monitors add` names a number and its line";
export const NO_WEBHOOK = "this org posts its alerts nowhere · `pinecall webhook set <url>` names a URL";
export const NO_COLLECTOR = "this org sends its traces nowhere · `pinecall telemetry set <url>` names a collector";

/** One monitor's rule, in words: `e2e_median_s above 2 over 7 days`. */
export function rule(monitor: Monitor): string {
  return `${monitor.metric} ${monitor.above ? "above" : "below"} ${monitor.threshold} over ${monitor.window_days} day${monitor.window_days === 1 ? "" : "s"}`;
}

export function monitors(found: Monitor[]): string[] {
  if (found.length === 0) return [NO_MONITORS];
  return table(
    ["id", "name", "rule", "agent", "fired"],
    found.map((one) => [one.id, one.name, rule(one), one.agent ?? "every agent", fired(one)]),
  );
}

export function monitor(one: Monitor): string {
  return `${one.id} · ${one.name} · ${rule(one)} · ${one.agent ?? "every agent"}`;
}

export function monitorRemoved({ id }: { id: string }): string {
  return `${id} forgotten`;
}

export function webhook(found: Webhook | null): string {
  if (found === null) return NO_WEBHOOK;
  return `alerts go to ${found.url} · ${found.signed ? "signed" : "not signed: set it again with --secret to sign every post"}`;
}

export function webhookTested(_tested: WebhookTest): string {
  return "the URL took it: a signed webhook.test post answered 2xx";
}

export function webhookCleared(): string {
  return "alerts stay on the agents' logs · the webhook forgotten";
}

export function collector(found: Collector | null): string {
  if (found === null) return NO_COLLECTOR;
  const headers = found.header_names.length > 0 ? ` · headers ${found.header_names.join(", ")}` : "";
  return `traces go to ${found.endpoint}${headers}${found.pii ? " · with what was said" : " · words stripped"}`;
}

export function collectorCleared(): string {
  return "the export stopped · the collector forgotten";
}

function fired(monitor: Monitor): string {
  return monitor.fired_on === null ? "never fired" : `fired ${monitor.fired_on} at ${monitor.fired_value}`;
}

/** What an alert is about, read off its data: the monitor, the app, the quota; the org's spend has none. */
function about(one: Alert): string {
  const named = one.data["name"] ?? one.data["app"] ?? one.data["quota"];
  return typeof named === "string" ? named : "—";
}

export function alerts(found: Alert[]): string[] {
  if (found.length === 0) return [NO_ALERTS];
  return table(
    ["when", "kind", "about", "agent", "mailed"],
    found.map((one) => [one.at.slice(0, 16).replace("T", " "), one.kind, about(one), one.agent ?? "—", one.mailed ? "yes" : "no"]),
  );
}
