/** Calls as a terminal reads them: the list, one call, its log, a chat's lines, the desk, the org's data. */

import type { CamelEvent } from "@pinecall/agents/client";
import type { Cost } from "@pinecall/agents/wire";

import { amount, count, date, duration, formatHint, formatPairs, money as dollars } from "../kit/format.js";
import { table } from "../kit/table.js";
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

/** The agent's calls, newest first, as a table: the id, how it came, how long, why it ended, what it cost, the agent's last words. */
export function sessions({ agent, calls }: { agent: string; calls: SessionLine[] }): string[] {
  if (calls.length === 0) return [`${agent} has run no calls`];
  const rows = table(
    ["call", "via", "lasted", "ended", "cost", "last said"],
    calls.map((one) => [one.call, [one.channel, one.direction].filter((word) => word !== null && word !== undefined).join(" ") || "—", lasted(one), endedOf(one), money(one.cost), onOneLine(one.outcome, 60)]),
  );
  return [`${agent} · ${count(calls.length, "call")}`, ...rows, formatHint(`pinecall sessions <call> reads one whole`)];
}

/** One call whole: live or not, its outcome, how it ended, what it cost, how each judge answered. */
export function call(shown: CallShown): string[] {
  const lines = [shown.call];
  const facts: [string, string][] = [];
  // A live call has no summary or score yet; say it is live rather than "not judged".
  if (shown.live) facts.push(["live", "still running"]);
  const summary = shown.summary;
  if (summary !== undefined) {
    facts.push(["outcome", String(summary["outcome"] ?? "—")]);
    facts.push(["ended", `${words(summary["reason"] ?? "—")} · ${duration(Number(summary["duration_s"] ?? 0))} · ${count(Number(summary["turns"] ?? 0), "turn")}`]);
    const cost = summary["cost"] as Cost | null | undefined;
    facts.push(["cost", money(cost)]);
  }
  const judged = scoreLines(shown.score);
  facts.push(["score", judged.headline]);
  const width = Math.max(...facts.map(([label]) => label.length));
  for (const [label, said] of facts) {
    lines.push(`  ${label.padEnd(width)}  ${said}`);
    if (label === "cost") lines.push(...costLines(summary?.["cost"] as Cost | null | undefined).map((row) => `  ${"".padEnd(width)}  ${row}`));
  }
  if (judged.judges.length > 0) lines.push("", ...judged.judges);
  lines.push(formatHint(shown.live ? `pinecall supervise ${shown.call} is the desk for it` : `pinecall sessions log ${shown.call} reads every entry`));
  return lines;
}

/**
 * A call.score: the headline (how many judges broke of how many that held or broke), then the
 * judges — those that broke first with their reason, those that held, a classification with what it
 * answered, and the ones that did not apply named on one line.
 */
export function scoreLines(score: Record<string, unknown> | undefined): { headline: string; judges: string[] } {
  if (score === undefined) return { headline: "not judged: this call carries no score", judges: [] };
  const why = score["not_judged"];
  if (typeof why === "string" && why !== "") return { headline: `not judged: ${why}`, judges: [] };
  const judges = (score["judges"] ?? []) as { name: string; verdict: string; criteria: string; reason: string; choice?: string | null; score?: number | null }[];
  const broke = judges.filter((one) => one.verdict === "broken");
  const held = judges.filter((one) => one.verdict === "held");
  const cost = score["judge_cost_usd"];
  const paid = typeof cost === "number" ? ` · ${dollars(cost)}` : "";
  const billed = score["own_key"] === true ? " · own key: evals not billed" : "";
  const settled = broke.length + held.length;
  const verdict = broke.length > 0 ? `${BROKEN} ${broke.length} of ${count(settled, "judge")} broke` : settled > 0 ? `${HELD} ${settled === 1 ? "the judge" : `all ${settled} judges`} held` : "– no judge held or broke";
  const width = Math.max(0, ...judges.map((one) => one.name.length));
  const answered = (judge: (typeof judges)[number]): string | undefined => judge.choice ?? (judge.score === null || judge.score === undefined ? undefined : `${judge.score}/5`);
  const lines = [
    ...broke.map((judge) => `  ${BROKEN} ${judge.name.padEnd(width)}  ${onOneLine(judge.reason, ROOM)}`),
    ...held.map((judge) => `  ${HELD} ${judge.name}`),
    ...judges.filter((one) => answered(one) !== undefined).map((judge) => `  ${MARKS["classified"]} ${judge.name.padEnd(width)}  ${answered(judge)}: ${onOneLine(judge.reason, ROOM)}`),
  ];
  const others = judges.filter((one) => one.verdict !== "broken" && one.verdict !== "held" && answered(one) === undefined);
  if (others.length > 0) lines.push(`  ${MARKS["na"]} ${others.map((one) => one.name).join(" · ")}  did not apply`);
  return { headline: `${verdict}${paid}${billed}`, judges: lines };
}

// Entries that say how the agent's machinery moved, not what was said or done: shown with --verbose.
const QUIET = new Set(["agent.state", "user.state", "prompt.changed", "agent.waiting"]);

/** The page, as lines: one per entry (the quiet ones only with `every`), then how to read on while there is more. */
export function log(page: LogPage, after: number, every = false): string[] {
  const shown = every ? page.entries : page.entries.filter((entry) => !QUIET.has(entry.type));
  const left = page.entries.length - shown.length;
  // A page the types narrowed can keep nothing and still have more after it.
  const width = Math.max(0, ...shown.map((entry) => entry.type.length));
  const nothing = page.next === null ? `${page.call} · nothing kept after seq ${after}` : `${page.call} · nothing of these types in this page, after seq ${after}; the log goes on`;
  const head = `${page.call} · ${count(shown.length, "entry", "entries")}${left === 0 ? "" : `, ${left} quiet left out`}`;
  const lines = page.entries.length === 0 ? [nothing] : [head, ...shown.map((entry) => entryLine(entry, width))];
  const steps = [...(left === 0 ? [] : ["--verbose shows every entry"]), ...(page.next === null ? [] : [`pinecall sessions log ${page.call} --after ${page.next} reads on`])];
  if (steps.length > 0) lines.push(formatHint(...steps));
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
    // A turn is one line however the model broke it: a terminal reads the transcript a turn a line.
    case "turn.user":
      return { mark: CALLER, text: folded(event.data.text) };
    case "turn.agent":
      return { mark: AGENT, text: folded(event.data.text) };
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
  const took = `${count(one.calls, "call")}, ${count(one.entries, "entry", "entries")}, ${count(one.memories, "memory", "memories")}, ${count(one.recordings, "recording")}`;
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
  const { retention_days: days, calling_hours: hours, per_number_day: most, disclosure } = row.policy;
  const kept = days === null || days === undefined ? "every sealed call is kept until it is erased" : `a sealed call is erased ${count(days, "day")} after it started`;
  // The +1 floor holds whatever the org sets: said whenever the setting is wider than it, or unset.
  const hoursFloor = hours === null || hours === undefined || hours.from < 8 || hours.until > 21 ? " (a +1 number: 8-21)" : "";
  const countFloor = most === null || most === undefined || most > 3 ? " (a +1 number: 3)" : "";
  const rung = hours === null || hours === undefined ? `a number is rung at any hour of its day${hoursFloor}` : `a number is rung from ${hours.from}:00 to ${hours.until}:00 of its own day${hoursFloor}`;
  const often = most === null || most === undefined ? `no limit of calls to one number a day${countFloor}` : `one number is rung at most ${count(most, "time")} a day${countFloor}`;
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
  if (page.next !== null) lines.push(formatHint(`--after ${page.next} reads on`));
  return lines;
}

export function doNotCallAdded(done: DoNotCallImported): string {
  return `${count(done.added, "number")} on the list${done.refused.length === 0 ? "" : ` · not numbers: ${done.refused.join(", ")}`}`;
}

/** Collapse whitespace and truncate to `width` with an ellipsis. */
export function onOneLine(said: string | null | undefined, width = 90): string {
  const folded = (said ?? "").replace(/\s+/g, " ").trim();
  return folded.length <= width ? folded : `${folded.slice(0, width - 1)}…`;
}

/** One line per priced row (the model, the ears, the voice, each phone leg) as aligned columns, then what had no rate. */
export function costLines(cost: Cost | null | undefined): string[] {
  if (cost === null || cost === undefined) return [];
  const rows = [
    ...cost.rows.map((row) => [row.model, `${amount(row.quantity)} ${words(row.unit)}`, `$${row.usd.toFixed(4)}`]),
    ...cost.unpriced.map((row) => [row.model, "no rate", "not counted"]),
  ];
  return table(["model", "used", "cost"], rows).slice(1);
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

function endedOf(one: SessionLine): string {
  return one.live === true ? "live" : words(one.end_reason ?? one.status ?? "—");
}

// `caller_hung_up` as a person says it: `caller hung up`.
function words(said: unknown): string {
  return String(said).replaceAll("_", " ");
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
        : `${String(data["name"])} → ${cut(folded(typeof data["summary"] === "string" ? data["summary"] : formatPairs(data["output"] ?? null)))}`;
    case "docs.sources":
      return sourcesLine(data);
    case "call.started":
      return startedLine(data);
    case "call.ended":
      return `${words(folded(data["reason"] ?? "ended"))}${typeof data["duration_s"] === "number" ? ` · ${duration(data["duration_s"])}` : ""}`;
    case "state.changed":
      return cut(stateLine(data));
    case "prompt.changed":
      return `${String(data["name"] ?? "")} · ${String(data["chars"] ?? 0)} chars`;
    case "tools.changed": {
      const visible = Array.isArray(data["visible"]) ? (data["visible"] as unknown[]).map(String) : [];
      return visible.length === 0 ? "none visible" : `visible: ${visible.join(", ")}`;
    }
    case "agent.waiting":
      return data["interrupted"] === true ? "the caller cut it off" : "said whole";
    case "error":
      return `${String(data["code"] ?? "error")}: ${folded(data["message"])}${data["recoverable"] === true ? " · recovered" : ""}`;
    case "call.score":
      return scoreReading(data);
    case "call.summary":
      return summaryReading(data);
    default:
      return entry.type.startsWith("metrics.") ? metricsReading(data) : cut(folded(formatPairs(data)));
  }
}

// What the call cost, how it ended and the run it belongs to; the rows are `pinecall sessions <call>`'s.
function summaryReading(data: Record<string, unknown>): string {
  const cost = data["cost"] as Cost | null | undefined;
  const said = [money(cost)];
  if (typeof data["reason"] === "string") said.push(words(data["reason"]));
  if (typeof data["turns"] === "number") said.push(count(data["turns"], "turn"));
  if (typeof data["run"] === "string") said.push(`run ${data["run"]}`);
  return said.join(" · ");
}

// How the call came in: its channel and medium, who it is from, the run it belongs to, what it is expected to do.
function startedLine(data: Record<string, unknown>): string {
  const said = [data["channel"], data["medium"], data["direction"]].filter((word): word is string => typeof word === "string" && word !== "");
  if (typeof data["from"] === "string" && data["from"] !== "") said.push(`from ${data["from"]}`);
  if (typeof data["caller"] === "string" && data["caller"] !== "") said.push(`caller ${data["caller"]}`);
  if (typeof data["run"] === "string" && data["run"] !== "") said.push(`run ${data["run"]}`);
  if (Array.isArray(data["expects"]) && data["expects"].length > 0) said.push(`expects ${data["expects"].length}`);
  return said.join(" · ");
}

// Which fields moved, to what, and what moved them: `takeMessage set stage "done" · message {…}`.
function stateLine(data: Record<string, unknown>): string {
  const state = (data["state"] ?? {}) as Record<string, unknown>;
  const changed = Array.isArray(data["changed"]) ? (data["changed"] as unknown[]).map(String) : Object.keys(state);
  const cause = data["cause"] as { kind?: string; tool?: string } | undefined;
  const by = cause === undefined ? "" : `${cause.tool ?? cause.kind ?? "something"} set `;
  return `${by}${changed.map((name) => formatPairs({ [name]: state[name] })).join(" · ")}`;
}

// The times livekit measured, in milliseconds, and the model that took them.
function metricsReading(data: Record<string, unknown>): string {
  const said: string[] = [];
  for (const name of ["ttft", "ttfb", "duration", "end_of_utterance_delay", "transcription_delay", "audio_duration"]) {
    if (typeof data[name] === "number") said.push(`${name.replaceAll("_", " ")} ${Math.round(data[name] * 1000)} ms`);
  }
  const model = (data["metadata"] as { model_name?: unknown } | undefined)?.model_name;
  if (typeof model === "string") said.push(model);
  return said.length === 0 ? cut(folded(formatPairs(data))) : said.join(" · ");
}

// The headline `pinecall sessions <call>` opens its score with; that verb has each judge.
function scoreReading(data: Record<string, unknown>): string {
  return scoreLines(data).headline;
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

