/** Each number a monitor can watch, in words: what it is, its unit, and how a value of it is written. */

import type { MonitorMetric } from "./door";

export interface MetricWords {
  /** The short name a picker shows. */
  name: string;
  /** What it is, for the lede of the form. */
  means: string;
  /** How a line or a value is said: seconds, a share, dollars, a count. */
  said: (value: number) => string;
  /** The side that is the wrong one, as most people watch it. */
  above: boolean;
}

const seconds = (value: number): string => `${value.toFixed(2)} s`;
const share = (value: number): string => `${Math.round(value * 100)}%`;
const dollars = (value: number): string => `$${value.toFixed(2)}`;
const count = (value: number): string => `${Math.round(value)}`;

export const METRIC_WORDS: Record<MonitorMetric, MetricWords> = {
  e2e_median_s: { name: "End-to-end latency, median", means: "the caller's wait from their last word to the agent's first", said: seconds, above: true },
  llm_median_s: { name: "Time to first token, median", means: "the model's time to its first token", said: seconds, above: true },
  held_rate: { name: "Held rate", means: "the share of the judges' verdicts that held", said: share, above: false },
  escalated_rate: { name: "Escalation rate", means: "the share of calls a person took over", said: share, above: true },
  tool_failure_rate: { name: "Tool failure rate", means: "the share of tool calls that answered an error", said: share, above: true },
  spend_usd: { name: "Spend", means: "what the calls cost, every vendor, in US dollars", said: dollars, above: true },
  calls: { name: "Calls", means: "how many calls there were", said: count, above: true },
};

/** Every metric, in the order the picker lists them. */
export const METRICS = Object.keys(METRIC_WORDS) as MonitorMetric[];

/** Whether a string the gateway sent names a metric this page knows. */
export function isMetric(metric: string): metric is MonitorMetric {
  return metric in METRIC_WORDS;
}

/** A monitor's rule, in words: `End-to-end latency, median above 2.00 s over 7 days`. */
export function ruleOf(monitor: { metric: string; above: boolean; threshold: number; window_days: number }): string {
  const words = isMetric(monitor.metric) ? METRIC_WORDS[monitor.metric] : undefined;
  const line = words === undefined ? `${monitor.threshold}` : words.said(monitor.threshold);
  return `${words?.name ?? monitor.metric} ${monitor.above ? "above" : "below"} ${line} over ${monitor.window_days} day${monitor.window_days === 1 ? "" : "s"}`;
}

/** A value of the metric, said in its unit. */
export function valueOf(metric: string, value: number): string {
  return isMetric(metric) ? METRIC_WORDS[metric].said(value) : `${value}`;
}
