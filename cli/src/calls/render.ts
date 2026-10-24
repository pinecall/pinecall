/** Calls as a terminal reads them: the list, one call, its log, a chat's lines, the desk, the org's data. */

import type { CamelEvent } from "@pinecall/agents/client";
import type { Cost } from "@pinecall/agents/wire";

import { date, duration, money as dollars } from "../kit/format.js";
import { BROKEN, HELD } from "../judging/render.js";
import type { CallShown, ConsentHistory, DoNotCall, DoNotCallImported, Entry, Erasure, ErasureTrail, LogPage, OrgPolicyRow, Reads, SessionLine } from "./service/index.js";

export { BROKEN, HELD };

// Glyphs, not colours: output is read over ssh, grepped and pasted.
export const CALLER = "‹";
export const AGENT = "›";
export const ASKS = "→";
export const ANSWERS = "←";
export const BROKE = "✗";

// Max characters of a judge's text per line; `--json` has the full text.
const ROOM = 96;
const ENTRY_ROOM = 160;
// N/A did not apply, = a classification (a choice or a score), · never asked, ? not settled.
const MARKS: Record<string, string> = { held: HELD, broken: BROKEN, na: "–", classified: "=", skipped: "·", deferred: "?" };

export const NOTHING_ERASED = "nothing erased yet";
export const NOBODY_READ = "nobody read a call of this org yet";
export const DNC_EMPTY = "nobody is on the do-not-call list";

/** One formatted line and its kind mark. */
export interface Line {
  mark: string;
  text: string;
}

/** The agent's calls, newest first: when, how long, why it ended, what it cost, the outcome. */
export function sessions({ agent, calls }: { agent: string; calls: SessionLine[] }): string[] {
  if (calls.length === 0) return [`${agent} has run no calls`];
  return [`${agent} · ${calls.length} call${calls.length === 1 ? "" : "s"}`, "", ...calls.map(sessionLine)];
}

/** One call as a list row: channel, duration, end reason, cost, outcome. */
export function sessionLine(one: SessionLine): string {
  const held = one.live === true ? "●" : " ";
  const channels = `${one.channel ?? "—"} ${one.direction ?? "—"}`.padEnd(15);
  const ending = one.live === true ? "live" : (one.end_reason ?? one.status ?? "—");
  return `${held} ${one.call.padEnd(38)} ${channels} ${lasted(one).padStart(7)}  ${ending.padEnd(20)} ${money(one.cost).padStart(8)}  ${onOneLine(one.outcome)}`.trimEnd();
}

/** One call whole: live or not, its outcome, how it ended, what it cost, how it was judged. */
export function call(shown: CallShown): string[] {
  const lines = [shown.call, ""];
  // A live call has no summary or score yet; say it is live rather than "not judged".
  if (shown.live) lines.push("  live      this call is still running — `pinecall supervise` is the desk for it", "");
  const summary = shown.summary;
  if (summary !== undefined) {
    lines.push(`  outcome   ${String(summary["outcome"] ?? "—")}`);
    lines.push(`  ended     ${String(summary["reason"] ?? "—")} · ${duration(Number(summary["duration_s"] ?? 0))} · ${String(summary["turns"] ?? 0)} turns`);
    const cost = summary["cost"] as Cost | null | undefined;
    lines.push(`  cost      ${money(cost)}`, ...costLines(cost));
  }
  lines.push(...scoreLines(shown.score));
  return lines;
}

/** A call.score: the verdict, then one line per judge, with the reason for failures and what a classification answered. */
export function scoreLines(score: Record<string, unknown> | undefined): string[] {
  if (score === undefined) return ["  score     not judged: this call carries no call.score"];
  const why = score["not_judged"];
  if (typeof why === "string" && why !== "") return [`  score     not judged: ${why}`];
  const judges = (score["judges"] ?? []) as { name: string; verdict: string; criteria: string; reason: string; choice?: string | null; score?: number | null }[];
  const passed = score["passed"];
  const judgeCalls = Number(score["judge_calls"] ?? 0);
  const evals = Number(score["evals"] ?? 0);
  const cost = score["judge_cost_usd"];
  const paid = typeof cost === "number" ? ` · ${dollars(cost)}` : "";
  const billed = score["own_key"] === true ? " · own key: evals not billed" : "";
  const headline = passed === true ? `${HELD} every judge held` : passed === false ? `${BROKEN} a judge answered broken` : "– no judge held or broke";
  const lines = [`  score     ${headline} · ${judges.length} judges · ${judgeCalls} model call${judgeCalls === 1 ? "" : "s"} · ${evals} eval${evals === 1 ? "" : "s"}${paid}${billed}`, ""];
  const width = Math.max(0, ...judges.map((one) => one.name.length));
  for (const judge of judges) {
    // Folded: some judges put their whole evidence in `criteria`.
    lines.push(`  ${MARKS[judge.verdict] ?? "·"} ${judge.name.padEnd(width)}  ${onOneLine(judge.criteria, ROOM)}`);
    const answered = judge.choice ?? (judge.score === null || judge.score === undefined ? undefined : `${judge.score}/5`);
    if (answered !== undefined) lines.push(`    ${" ".repeat(width)}  ${answered}: ${onOneLine(judge.reason, ROOM)}`);
    else if (judge.verdict !== "held") lines.push(`    ${" ".repeat(width)}  ${onOneLine(judge.reason, ROOM)}`);
  }
  return lines;
}

/** The page, as lines: one per entry, then how to read on while there is more. */
export function log(page: LogPage, after: number): string[] {
  // A page the types narrowed can keep nothing and still have more after it.
  const width = Math.max(0, ...page.entries.map((entry) => entry.type.length));
  const nothing = page.next === null ? `${page.call} · nothing kept after seq ${after}` : `${page.call} · nothing of these types in this page, after seq ${after}; the log goes on`;
  const lines = page.entries.length === 0 ? [nothing] : page.entries.map((entry) => entryLine(entry, width));
  if (page.next !== null) lines.push("", `more: pinecall sessions log ${page.call} --after ${page.next}`);
  return lines;
}

/** One entry on one line: its seq, its time, its type, and what it says. */
export function entryLine(entry: Entry, width = entry.type.length): string {
  const at = entry.ts === undefined ? "".padEnd(12) : new Date(entry.ts * 1000).toISOString().slice(11, 23);
  return `${String(entry.seq).padStart(6)}  ${at}  ${entry.type.padEnd(width)}  ${entryReading(entry)}`.trimEnd();
}

/** An event as a line, or null for events that have none. Shared with `start`'s screens. */
export function lineFor(event: CamelEvent): Line | null {
  switch (event.type) {
    case "turn.user":
      return { mark: CALLER, text: String(event.data.text ?? "") };
    case "turn.agent":
      return { mark: AGENT, text: String(event.data.text ?? "") };
    case "tool.call":
      return { mark: ASKS, text: `${event.data.name}(${short(event.data.arguments)})` };
    case "tool.result":
      return { mark: ANSWERS, text: toolResultLine(event.data) };
    default:
      return null;
  }
}

// Per-turn LiveKit metrics, in display order. Missing ones are omitted, never shown as zero.
export const TURN_METRICS = ["e2e_latency", "llm_node_ttft", "tts_node_ttfb"] as const;

/** Format a turn's latencies in milliseconds. */
export function metricsLine(metrics: Record<string, unknown> | undefined): string {
  const parts: string[] = [];
  for (const name of TURN_METRICS) {
    const value = metrics?.[name];
    if (typeof value === "number") parts.push(`${name} ${Math.round(value * 1000)}ms`);
  }
  return parts.length === 0 ? "no metrics on this turn" : parts.join("  ");
}

/** A chat frame as a line; null for entries with no line. `turn.user` is skipped: readline already echoed it. */
export function chatLine(entry: Entry): string | null {
  if (entry.type === "turn.user") return null;
  if (entry.type === "error") return `${BROKE} ${String(entry.data["message"])}`;
  const line = lineFor({ type: entry.type, data: entry.data } as CamelEvent);
  return line === null ? null : `${line.mark} ${line.text}`;
}

/** A log entry for the desk: turns, supervisor moves and the end; null for everything else. */
export function deskLine(entry: Entry): string | null {
  const at = String(entry.seq).padStart(4, " ");
  const data = entry.data;
  if (entry.type === "turn.user") return `${at}  caller  ${String(data["text"] ?? "")}`;
  if (entry.type === "turn.agent") return `${at}  agent   ${String(data["text"] ?? "")}`;
  if (entry.type === "call.ended") return `${at}  ——      ended: ${String(data["reason"] ?? "")}`;
  if (entry.type.startsWith("supervisor.")) {
    const what = entry.type.slice("supervisor.".length);
    const said = data["text"] ?? data["reason"] ?? data["to"] ?? "";
    return `${at}  desk    ${what}${said === "" ? "" : ` ${String(said)}`}`;
  }
  return null;
}

export function erased(one: Erasure): string {
  const took = `${one.calls} call(s), ${one.entries} entries, ${one.memories} memories, ${one.recordings} recording(s)`;
  return `${date(one.at)}  ${one.what} ${one.subject}  ${took}  by ${one.asked_by}`;
}

export function erasures(trail: ErasureTrail): string[] {
  return trail.erasures.length === 0 ? [NOTHING_ERASED] : trail.erasures.map(erased);
}

export function reads(found: Reads): string[] {
  if (found.reads.length === 0) return [NOBODY_READ];
  return found.reads.map((read) => `${date(read.at)}  ${read.what.padEnd(9)}  ${read.subject}  by ${read.reader}${read.env === null ? "" : `  (${read.env})`}`);
}

/** The policy as one sentence a setting, and who set it. */
export function policy(row: OrgPolicyRow): string[] {
  const { retention_days: days, calling_hours: hours, per_number_day: count, disclosure } = row.policy;
  const kept = days === null || days === undefined ? "every sealed call is kept until it is erased" : `a sealed call is erased ${days} day(s) after it started`;
  // The +1 floor holds whatever the org sets: said whenever the setting is wider than it, or unset.
  const hoursFloor = hours === null || hours === undefined || hours.from < 8 || hours.until > 21 ? " (a +1 number: 8-21)" : "";
  const countFloor = count === null || count === undefined || count > 3 ? " (a +1 number: 3)" : "";
  const rung = hours === null || hours === undefined ? `a number is rung at any hour of its day${hoursFloor}` : `a number is rung from ${hours.from}:00 to ${hours.until}:00 of its own day${hoursFloor}`;
  const often = count === null || count === undefined ? `no limit of calls to one number a day${countFloor}` : `one number is rung at most ${count} time(s) a day${countFloor}`;
  const consent = row.policy.consent_everywhere === true ? "every number needs a consent on file" : "a +1 number needs a consent on file";
  const opens = disclosure === null || disclosure === undefined ? 'the platform\'s sentence ("This is an automated assistant calling on behalf of …")' : disclosure === "" ? "nothing: the agent's own greeting must disclose it" : `"${disclosure}"`;
  const notice = row.policy.recording_notice === false ? "a recorded call says nothing of it" : 'a recorded call says "This call may be recorded."';
  const by = row.set_by === null ? "nobody set it" : `set by ${row.set_by}`;
  return [`retention:      ${kept}`, `calling hours:  ${rung}`, `per number:     ${often}`, `consent:        ${consent}`, `outbound opens: ${opens}`, `recording:      ${notice}`, by];
}

export function consent(history: ConsentHistory): string[] {
  const said = { consented: "consented", opted_out: "on the do-not-call list", unknown: "nothing on file" }[history.standing];
  return [
    `${history.number}  ${said}`,
    ...history.rows.map((row) => `  ${date(row.given_at)}  ${row.kind.padEnd(8)}  ${row.source}  by ${row.given_by}${row.call === null ? "" : `  on ${row.call}`}`),
  ];
}

export function doNotCall(page: DoNotCall): string[] {
  const lines = page.numbers.length === 0 ? [DNC_EMPTY] : page.numbers.map((opted) => `${opted.number}  since ${date(opted.since)}  ${opted.source}  by ${opted.given_by}`);
  if (page.next !== null) lines.push(`more: --after ${page.next}`);
  return lines;
}

export function doNotCallAdded(done: DoNotCallImported): string {
  return `${done.added} number(s) on the list${done.refused.length === 0 ? "" : ` · not numbers: ${done.refused.join(", ")}`}`;
}

/** Collapse whitespace and truncate to `width` with an ellipsis. */
export function onOneLine(said: string | null | undefined, width = 90): string {
  const folded = (said ?? "").replace(/\s+/g, " ").trim();
  return folded.length <= width ? folded : `${folded.slice(0, width - 1)}…`;
}

/** One line per priced row (the model, the ears, the voice, each phone leg), then what had no rate. */
export function costLines(cost: Cost | null | undefined): string[] {
  if (cost === null || cost === undefined) return [];
  const rows = cost.rows.map((row) => `            ${`${row.provider} ${row.model}`.padEnd(44)} ${`${quantity(row.quantity)} ${row.unit}`.padEnd(26)} $${row.usd.toFixed(4)}`);
  const unpriced = cost.unpriced.map((row) => `            ${row.provider} ${row.model}`.padEnd(56) + " no rate: not counted");
  return [...rows, ...unpriced];
}

/** A call's cost in US dollars, or a dash when unpriced. */
export function money(cost: Cost | null | undefined): string {
  const total = cost?.usd;
  return typeof total === "number" ? `$${total.toFixed(4)}` : "—";
}

function lasted(one: SessionLine): string {
  if (one.started_at === null || one.started_at === undefined) return "—";
  const until = one.ended_at ?? Date.now() / 1000;
  return duration(until - one.started_at);
}

// What a person looks for in each kind of entry; every other kind is its data, folded and cut.
function entryReading(entry: Entry): string {
  const data = entry.data;
  switch (entry.type) {
    case "turn.user":
    case "turn.agent":
    case "user.transcript":
    case "agent.transcript":
      return `${folded(data["text"])}${data["interrupted"] === true ? "  (interrupted)" : ""}`;
    case "agent.state":
    case "user.state":
      return String(data["state"] ?? "");
    case "tool.call":
      return `${String(data["name"])}(${argumentsOf(data["arguments"])})`;
    case "tool.result":
      return typeof data["error"] === "string"
        ? `${String(data["name"])} refused: ${folded(data["error"])}`
        : `${String(data["name"])} → ${cut(folded(typeof data["summary"] === "string" ? data["summary"] : JSON.stringify(data["output"] ?? null)))}`;
    case "docs.sources":
      return sourcesLine(data);
    default:
      return cut(folded(JSON.stringify(data)));
  }
}

// Where each chunk came from, not what it says: the excerpts would cut the line before the first heading.
function sourcesLine(data: Record<string, unknown>): string {
  const sources = Array.isArray(data["sources"]) ? (data["sources"] as Record<string, unknown>[]) : [];
  const found = sources.map((one) => {
    const where = [one["base"], one["path"]].filter((part) => typeof part === "string").join("/");
    const heading = typeof one["heading"] === "string" && one["heading"] !== "" ? ` › ${one["heading"]}` : "";
    const score = typeof one["score"] === "number" ? ` ${one["score"].toFixed(2)}` : "";
    return `${where}${heading}${score}`;
  });
  return cut(`"${folded(data["query"])}" → ${found.length === 0 ? "nothing" : found.join(" · ")}`);
}

function toolResultLine(data: { name?: string | undefined; output?: unknown; error?: unknown; summary?: string | null | undefined }): string {
  if (data.error !== undefined && data.error !== null) return `${data.name ?? "tool"} error: ${short(data.error)}`;
  // A void tool has no output field (JSON has no undefined).
  const answered = data.summary ?? (data.output === undefined ? "nothing" : short(data.output));
  return `${data.name ?? "tool"} ${answered}`;
}

function argumentsOf(given: unknown): string {
  if (given === null || typeof given !== "object") return "";
  return Object.entries(given as Record<string, unknown>)
    .map(([name, value]) => `${name}=${typeof value === "string" ? folded(value) : JSON.stringify(value)}`)
    .join(", ");
}

// JSON, truncated to `width`.
function short(value: unknown, width = 60): string {
  const text = typeof value === "string" ? value : (JSON.stringify(value) ?? String(value));
  return text.length > width ? `${text.slice(0, width - 1)}…` : text;
}

function folded(said: unknown): string {
  return String(said ?? "").replace(/\s+/g, " ").trim();
}

function cut(said: string): string {
  return said.length <= ENTRY_ROOM ? said : `${said.slice(0, ENTRY_ROOM - 1)}…`;
}

function quantity(amount: number): string {
  return Number.isInteger(amount) ? amount.toLocaleString("en-US") : amount.toFixed(1);
}
