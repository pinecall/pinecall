/** Monitors and alerts in the page's words: each number watched and how a value of it is said, a rule as a sentence, and what an alert is about. */

import type { Alert, Monitor, MonitorMetric } from "./door";

interface Metric {
  name: string;
  /** What it is, under the picker. */
  means: string;
  /** How the line is typed: its unit, and an example. */
  unit: string;
  example: string;
  said: (value: number) => string;
  /** A share is typed as a percentage and kept as 0 to 1. */
  share: boolean;
  /** The side most people watch. */
  above: boolean;
}

const seconds = (value: number): string => `${value.toFixed(2)} s`;
const share = (value: number): string => `${Math.round(value * 100)}%`;
const dollars = (value: number): string => `$${value.toFixed(2)}`;
const count = (value: number): string => `${Math.round(value)}`;

export const METRICS: Record<MonitorMetric, Metric> = {
  e2e_median_s: { name: "Response time", means: "How long the caller waits from their last word to the agent's first, at the median.", unit: "seconds", example: "2", said: seconds, share: false, above: true },
  llm_median_s: { name: "Model's first token", means: "How long the model takes to start answering, at the median.", unit: "seconds", example: "0.8", said: seconds, share: false, above: true },
  held_rate: { name: "Judges held", means: "The share of the judges' verdicts that held.", unit: "%", example: "90", said: share, share: true, above: false },
  escalated_rate: { name: "Escalations", means: "The share of calls a person took over.", unit: "%", example: "10", said: share, share: true, above: true },
  tool_failure_rate: { name: "Tool failures", means: "The share of tool calls that answered an error.", unit: "%", example: "5", said: share, share: true, above: true },
  spend_usd: { name: "Spend", means: "What the calls cost, every vendor, in US dollars.", unit: "dollars", example: "5", said: dollars, share: false, above: true },
  calls: { name: "Calls", means: "How many calls there were.", unit: "calls", example: "100", said: count, share: false, above: true },
};

const metricOf = (metric: string): Metric | undefined => (metric in METRICS ? METRICS[metric as MonitorMetric] : undefined);

/** A value of a metric, in its unit. */
export function valueOf(metric: string, value: number): string {
  return metricOf(metric)?.said(value) ?? String(value);
}

const WINDOWS: Record<number, string> = { 1: "a day", 7: "7 days", 30: "30 days" };

/** A monitor's rule as a sentence: `Response time above 2.00 s over 7 days`. */
export function ruleOf(monitor: Pick<Monitor, "metric" | "above" | "threshold" | "window_days">): string {
  return `${metricOf(monitor.metric)?.name ?? monitor.metric} ${monitor.above ? "above" : "below"} ${valueOf(monitor.metric, monitor.threshold)} over ${WINDOWS[monitor.window_days] ?? `${monitor.window_days} days`}`;
}

/** The days since a day `2026-11-05`, in UTC. */
function daysSince(day: string, now: number = Date.now()): number {
  return Math.max(0, Math.floor((now - Date.parse(`${day}T00:00:00Z`)) / 86_400_000));
}

/** How a monitor stands: it fired inside its own window, it fired before that, or it never did. */
export function standingOf(monitor: Monitor): { mood: "broke" | "held" | "none"; said: string } {
  if (monitor.fired_on === null) return { mood: "none", said: "Never fired" };
  const days = daysSince(monitor.fired_on);
  const when = days === 0 ? "today" : days === 1 ? "yesterday" : `${days} d ago`;
  const at = monitor.fired_value === null ? "" : ` at ${valueOf(monitor.metric, monitor.fired_value)}`;
  return { mood: days <= monitor.window_days ? "broke" : "held", said: `Fired ${when}${at}` };
}

const KINDS: Record<string, string> = {
  "monitor.fired": "A monitor fired",
  "spend.unusual": "Unusual spend",
  "credits.exhausted": "Out of quota",
  "vendor.failed": "A vendor failed a call",
  "org.quiet": "A new org is quiet",
  "app.failed": "An app went down",
};

const worded = (value: unknown): string | null => (typeof value === "string" && value !== "" ? value : null);

/** An alert in a line: what happened, and what it was about. */
export function alertOf(alert: Alert): { title: string; about: string } {
  const { data } = alert;
  const title = KINDS[alert.kind] ?? alert.kind;
  if (alert.kind === "monitor.fired" && typeof data["metric"] === "string" && typeof data["value"] === "number") {
    return { title: worded(data["name"]) ?? title, about: `${metricOf(data["metric"])?.name ?? data["metric"]} at ${valueOf(data["metric"], data["value"])}` };
  }
  if (alert.kind === "vendor.failed") return { title, about: [worded(data["vendor"]), worded(data["stage"])].filter((part) => part !== null).join(", ") };
  return { title, about: worded(data["name"]) ?? worded(data["app"]) ?? worded(data["quota"]) ?? worded(data["vendor"]) ?? "" };
}

/** What an alert carries, as rows a person reads: its data, long text cut where a row ends. */
export function factsOf(alert: Alert): { name: string; value: string }[] {
  return Object.entries(alert.data)
    .filter(([name, value]) => value !== null && value !== "" && name !== "env")
    .map(([name, value]) => ({ name: name.replace(/_/g, " "), value: typeof value === "number" && typeof alert.data["metric"] === "string" && (name === "value" || name === "threshold") ? valueOf(alert.data["metric"], value) : typeof value === "string" ? value : JSON.stringify(value) }));
}
