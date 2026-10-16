/** Agents as a terminal reads them: the settings table, versions, a diff, the lexicon, the pipeline, the apps, the voices. */

import type { TuningDiff, TuningHistory } from "@pinecall/agents/wire";

import type { CornerWritten } from "./service/corners.js";
import { date } from "../kit/format.js";
import { table } from "../kit/table.js";
import { DECLARED_AS, FIELDS, WIRE, type AppProcess, type Field, type LexiconAnswer, type LexiconHistory, type LexiconRow, type ListedVoice, type PipelineReport, type Pulled, type TuningAnswer, type TuningBody, type TuningRow, type VoicePlayed } from "./service/index.js";

// Max cell width; longer values are truncated so three columns fit.
const A_CELL = 40;

export const NO_APPS = "no app is connected here: `pinecall start` holds a project's agents";
export const NO_VOICES = "no voice matches: try another --language or --country";
export const UNCHANGED = "nothing changed: no version written";
export const NOTHING_KNOWN = (agent: string, corner: string): string => `${agent} knows nothing by heart in ${corner}: \`pinecall agent knowledge edit\` writes it`;

/**
 * The settings table: one column per corner, one row per field, then each corner's version. An
 * unset corner shows what it falls back to, e.g. `(team's)`; a field the class fixes says `class`
 * in every corner, since no corner's value is read for it.
 */
export function settings({ agent, answer }: { agent: string; answer: TuningAnswer }): string[] {
  const corners: { name: string; row: TuningRow | null; fallsTo: string }[] = [
    { name: "yours", row: answer.yours, fallsTo: "(team's)" },
    { name: "team", row: answer.team, fallsTo: "—" },
    { name: "production", row: answer.production, fallsTo: "—" },
  ];
  const fixed = new Set(answer.fixed);
  const cell = (corner: (typeof corners)[number], field: Field): string => {
    const declared = DECLARED_AS[field];
    if (declared !== undefined && fixed.has(declared)) return "class";
    if (corner.row === null) return corner.fallsTo;
    const value = shown(corner.row.config, field);
    if (value === undefined) return "—";
    return value.length > A_CELL ? `${value.slice(0, A_CELL - 1)}…` : value;
  };
  const widths = corners.map((corner) => Math.max(corner.name.length, ...FIELDS.map((field) => cell(corner, field).length)) + 2);
  const lines = [`${agent} · ${answer.world}`, ""];
  lines.push(`  ${"".padEnd(14)}${corners.map((corner, at) => corner.name.padEnd(widths[at]!)).join("")}`.trimEnd());
  for (const field of FIELDS) {
    lines.push(`  ${field.replace("-", " ").padEnd(14)}${corners.map((corner, at) => cell(corner, field).padEnd(widths[at]!)).join("")}`.trimEnd());
  }
  lines.push("");
  lines.push(`  ${corners.map((corner) => `${corner.name}: ${corner.row === null ? "nothing set" : versionLine(corner.row)}`).join(" · ")}`);
  return lines;
}

// `clinica-norte (k 4 · tool · min 0.3)`: what the attachment sets, nothing it leaves to the default.
function baseLine(one: { base: string; k?: number | null | undefined; mode?: string | null | undefined; min_score?: number | null | undefined }): string {
  const set = [one.k == null ? null : `k ${one.k}`, one.mode ?? null, one.min_score == null ? null : `min ${one.min_score}`].filter((word) => word !== null);
  return set.length === 0 ? one.base : `${one.base} (${set.join(" · ")})`;
}

/** One field of one config, as a cell of the page; undefined when the config does not set it. */
export function shown(config: TuningBody, field: Field): string | undefined {
  // The wire sends either absent or null for "not set".
  if (field === "greeting") {
    const greeting = config.greeting ?? undefined;
    if (greeting === undefined) return undefined;
    const say = greeting.say ?? undefined;
    const reply = greeting.reply ?? "";
    const opening = say !== undefined ? `"${say}"` : reply === "" ? "improvise" : `improvise: ${reply}`;
    return greeting.allow_interruptions === true ? `${opening} · interruptible` : opening;
  }
  if (field === "hangup") {
    const hangup = config.hangup ?? undefined;
    if (hangup === undefined) return undefined;
    return hangup.when === "" || hangup.when === null || hangup.when === undefined ? "may hang up" : `when ${hangup.when}`;
  }
  if (field === "turn") {
    const turn = config.turn ?? undefined;
    if (turn === undefined) return undefined;
    const said: string[] = [];
    if (turn.endpointing_ms !== undefined && turn.endpointing_ms !== null) said.push(`endpointing ${turn.endpointing_ms} ms`);
    if (turn.min_interruption_words !== undefined && turn.min_interruption_words !== null) said.push(`interrupt at ${turn.min_interruption_words} words`);
    if (turn.eot_threshold !== undefined && turn.eot_threshold !== null) said.push(`sure at ${turn.eot_threshold}`);
    if (turn.eager_eot_threshold !== undefined && turn.eager_eot_threshold !== null) said.push(`guesses at ${turn.eager_eot_threshold}`);
    return said.join(" · ");
  }
  if (field === "memory") {
    const memory = config.memory ?? undefined;
    if (memory === undefined) return undefined;
    return `remember ${memory.remember?.length ?? 0} · forget ${memory.forget?.length ?? 0}`;
  }
  // false is meaningful (no audio kept); undefined falls through to the next corner.
  if (field === "record") {
    const records = config.record ?? undefined;
    return records === undefined ? undefined : records ? "keeps the audio" : "keeps no audio";
  }
  // Zero means no limit.
  if (field === "max-duration") {
    const seconds = config.max_duration_s ?? undefined;
    return seconds === undefined ? undefined : seconds === 0 ? "no limit" : `${seconds / 60} min`;
  }
  if (field === "temperature") {
    const temperature = config.temperature ?? undefined;
    return temperature === undefined ? undefined : String(temperature);
  }
  if (field === "llm-options" || field === "stt-options" || field === "tts-options" || field === "judge-options") {
    const options = config[WIRE[field] as "llm_options"] ?? undefined;
    if (options === undefined) return undefined;
    return Object.entries(options).map(([key, value]) => `${key}=${JSON.stringify(value)}`).join(" · ");
  }
  if (field === "knowledge") {
    const text = config.knowledge ?? undefined;
    return text === undefined ? undefined : `${text.length.toLocaleString("en-US")} chars`;
  }
  if (field === "bases") {
    const bases = config.bases ?? undefined;
    if (bases === undefined || bases.length === 0) return undefined;
    return bases.map(baseLine).join(" · ");
  }
  const value = config[WIRE[field]];
  return typeof value === "string" ? value : undefined;
}

/** One version as a line: number, author, time and note. */
export function versionLine(row: { version: number; author: string; set_at: number; note: string | null }): string {
  const said = [`v${row.version}`, row.author, date(row.set_at)];
  if (row.note !== null) said.push(`"${row.note}"`);
  return said.join(" · ");
}

/** The fields that differ between two configs, each as `field before → after`. */
export function changes(before: TuningBody, after: TuningBody, lead: string, joined = " · "): string {
  const said: string[] = [];
  for (const field of FIELDS) {
    const was = shown(before, field);
    const is = shown(after, field);
    if (was === is) continue;
    said.push(`${field.replace("-", " ")} ${was ?? "—"} → ${is ?? "—"}`);
  }
  return said.length === 0 ? "" : `${lead}${said.join(joined === "\n" ? `\n${lead}` : joined)}`;
}

/** The versions of a corner, newest first, each with what it changed over the one before. */
export function history({ agent, history: kept }: { agent: string; history: TuningHistory }): string[] {
  const lines = [`${agent} · ${kept.world} · ${kept.holder === "" ? "the org's own corner" : `corner ${kept.holder}`}`];
  if (kept.rows.length === 0) return [...lines, "  nothing set yet"];
  // Each version is diffed against the previous one; the oldest against an empty config.
  kept.rows.forEach((row, at) => {
    const older = kept.rows[at + 1] ?? null;
    lines.push(`  ${versionLine(row)}${changes(older?.config ?? {}, row.config, "   ")}`);
  });
  return lines;
}

export function diff({ agent, against, diff: said }: { agent: string; against: string; diff: TuningDiff }): string[] {
  const ours = said.ours === null ? "nothing set" : `${said.ours.holder === "" ? "team" : "yours"} v${said.ours.version}`;
  const theirs = said.theirs === null ? "nothing set" : `v${said.theirs.version}`;
  const lines = [`${agent} · ${ours} vs ${against} ${theirs}`];
  if (said.changed.length === 0) return [...lines, "  the same"];
  return [...lines, changes(said.theirs?.config ?? {}, said.ours?.config ?? {}, "  ", "\n")];
}

export function pulled(one: Pulled): string {
  return JSON.stringify(one, null, 2);
}

export function pushed(done: CornerWritten & { file: string }): string {
  return `${done.agent} · ${done.answer.world} · ${done.corner} v${done.version ?? "?"} from ${done.file}`;
}

export function knowledge({ agent, corner, knowledge: text }: { agent: string; corner: string; knowledge: string | null }): string[] {
  if (text === null) return [NOTHING_KNOWN(agent, corner)];
  return text.replace(/\n$/, "").split("\n");
}

export function knowledgeWritten(done: CornerWritten, text: string): string {
  return `${done.agent} · knowledge ${text.trim() === "" ? "taken out" : `${text.length.toLocaleString("en-US")} chars`} · ${done.corner} v${done.version ?? "?"}`;
}

/** The effective lexicon, then each corner's version. */
export function lexicon(answer: LexiconAnswer): string[] {
  const read = answer.yours ?? answer.team;
  const lines = [`lexicon · ${answer.world}${answer.yours === null ? "" : " · your corner"}`];
  if (read === null) lines.push("  nothing set: the voice says every word as it is written");
  else {
    const spoken = read.lexicon.said.map((one) => `${one.word} → "${one.spoken}"`).join(" · ");
    lines.push(`  said     ${spoken || "—"}`);
    lines.push(`  heard    ${read.lexicon.heard.join(" · ") || "—"}`);
  }
  lines.push("");
  const corners: [string, LexiconRow | null][] = [["yours", answer.yours], ["team", answer.team], ["production", answer.production]];
  lines.push(`  ${corners.map(([name, row]) => `${name}: ${row === null ? "nothing set" : versionLine(row)}`).join(" · ")}`);
  return lines;
}

export function lexiconHistory(kept: LexiconHistory): string[] {
  const lines = [`lexicon · ${kept.world} · ${kept.holder === "" ? "the org's own corner" : `corner ${kept.holder}`}`];
  if (kept.rows.length === 0) lines.push("  nothing set yet");
  for (const row of kept.rows) lines.push(`  ${versionLine(row)}   said ${row.lexicon.said.length} · heard ${row.lexicon.heard.length}`);
  return lines;
}

/** The report: stages, greeting, latency medians, unavailable vendors. */
export function pipeline(report: PipelineReport): string[] {
  const calls = `${report.calls} call${report.calls === 1 ? "" : "s"}`;
  const lines = [`${report.agent} · ${calls}`, ""];
  lines.push(`  hears     ${stageLine(report.hears)}`);
  lines.push(`  decides   ${stageLine(report.decides)}`);
  lines.push(`  speaks    ${stageLine(report.speaks)}`);
  const opening = openingLine(report);
  if (opening !== "") lines.push("", `  greeting  ${opening}`);
  if (report.medians.length > 0) lines.push("", `  ${report.medians.map((one) => `${one.name} ${measured(one)}`).join(" · ")}`);
  const off = Object.entries(report.unavailable_reasons);
  if (off.length > 0) {
    lines.push("");
    for (const [vendor, why] of off) lines.push(`  ${vendor} is not available here: ${why}`);
  }
  return lines;
}

/** Every app connected in the env, one line each: id, agents, corner, host and address, SDK, connected since. */
export function apps(found: AppProcess[]): string[] {
  if (found.length === 0) return [NO_APPS];
  return found.map((app) => {
    const whose = app.holder === null ? "the org's" : (app.holder.name ?? app.holder.holder ?? "");
    const where = `${app.host ?? "an unnamed host"}${app.address === null ? "" : ` (${app.address})`}`;
    return `${app.app}  ${app.agents.join(", ") || "no agent yet"}  ${whose} · ${where} · ${app.sdk ?? "an unknown sdk"} · since ${date(app.connected_at)}`;
  });
}

export function appStopped({ app }: { app: string }): string {
  return `stopped ${app}: its agents are free — a supervisor that restarts it (systemd, pm2) starts it again`;
}

export function voices(found: ListedVoice[]): string[] {
  if (found.length === 0) return [NO_VOICES];
  return table(
    ["id", "name", "gender", "from"],
    found.map((voice) => [voice.id, voice.name, voice.gender, [voice.country, voice.accent].filter((word) => word !== "").join(" ")]),
  );
}

export function voicePlayed(played: VoicePlayed): string {
  const wait = played.firstAudioMs === null ? "—" : `${played.firstAudioMs} ms`;
  const whole = played.totalMs === null ? "—" : `${played.totalMs} ms`;
  return `${played.voice} · first audio ${wait} · whole sentence ${whole} · ${played.player}${played.kept ? ` · saved ${played.file}` : ""}`;
}

/** A median as its unit reads: a share of the talking as a percent, everything else in seconds. */
function measured(one: { name: string; seconds: number }): string {
  return one.name === "talk_share" ? `${Math.round(one.seconds * 100)}%` : `${one.seconds.toFixed(2)}s`;
}

function stageLine(stage: { vendor: string; model: string | null; voice_id: string | null; language: string | null }): string {
  const said = [stage.vendor, stage.model, stage.voice_id, stage.language];
  return said.filter((word): word is string => typeof word === "string" && word !== "").join(" · ");
}

function openingLine(report: PipelineReport): string {
  const greeting = report.greeting;
  if (greeting === null) return "";
  if (greeting.say !== null && greeting.say !== "") return `"${greeting.say}"`;
  return `the model improvises: ${greeting.reply ?? ""}`;
}
