/** Agents as a terminal reads them: the settings table, versions, a diff, the lexicon, the pipeline, the apps, the voices, the walks. */

import type { TuningDiff, TuningHistory } from "@pinecall/agents/wire";

import type { CornerWritten } from "./service/corners.js";
import { count, date, duration, formatHint, formatNotice } from "../kit/format.js";
import { table } from "../kit/table.js";
import { DECLARED_AS, FIELDS, WIRE, type AppProcess, type Field, type KilledAgent, type LexiconAnswer, type LexiconHistory, type LexiconRow, type HoldMelody, type ListedVoice, type PipelineReport, type Pulled, type TuningAnswer, type TuningBody, type TuningRow, type VoicePlayed, type WalkListed, type WalkPlayed } from "./service/index.js";

// Max cell width; longer values are truncated so three columns fit.
const A_CELL = 40;

export const NO_APPS = "no app is connected here: `pinecall start` holds a project's agents";
export const NO_VOICES = "no voice matches: try another --language or --country";
export const NO_WALKS = (agent: string): string => `${agent} published no walks: a Tutor records its macros as \`pinecall start\` holds it`;
export const UNCHANGED = "nothing changed: no version written";
export const NOTHING_KNOWN = (agent: string, corner: string): string => `${agent} knows nothing by heart in ${corner}: \`pinecall agent knowledge edit\` writes it`;

export const NOTHING_SET = "nothing set in any corner · the class and the runtime's defaults answer";

/**
 * The settings table: one column per corner, one row per field some corner sets or the class fixes,
 * then each corner's version and how many fields are set nowhere. An unset corner shows what it
 * falls back to, e.g. `(team's)`; a field the class fixes says `class` in every corner, since no
 * corner's value is read for it.
 */
export function settings({ agent, answer }: { agent: string; answer: TuningAnswer }): string[] {
  const corners: { name: string; row: TuningRow | null; fallsTo: string }[] = [
    { name: "yours", row: answer.yours, fallsTo: "(team's)" },
    { name: "team", row: answer.team, fallsTo: "—" },
    { name: "production", row: answer.production, fallsTo: "—" },
  ];
  const fixed = new Set(answer.fixed);
  const declared = (field: Field): boolean => {
    const as = DECLARED_AS[field];
    return as !== undefined && fixed.has(as);
  };
  const cell = (corner: (typeof corners)[number], field: Field): string => {
    if (declared(field)) return "class";
    if (corner.row === null) return corner.fallsTo;
    const value = shown(corner.row.config, field);
    if (value === undefined) return "—";
    return value.length > A_CELL ? `${value.slice(0, A_CELL - 1)}…` : value;
  };
  const set = FIELDS.filter((field) => declared(field) || corners.some((corner) => corner.row !== null && shown(corner.row.config, field) !== undefined));
  const lines = [`${agent} · ${answer.world}`];
  if (set.length === 0) lines.push(`  ${NOTHING_SET}`);
  else {
    const widths = corners.map((corner) => Math.max(corner.name.length, ...set.map((field) => cell(corner, field).length)) + 2);
    const label = Math.max(...set.map((field) => field.length)) + 2;
    lines.push("", `  ${"".padEnd(label)}${corners.map((corner, at) => corner.name.padEnd(widths[at]!)).join("")}`.trimEnd());
    for (const field of set) {
      lines.push(`  ${field.replaceAll("-", " ").padEnd(label)}${corners.map((corner, at) => cell(corner, field).padEnd(widths[at]!)).join("")}`.trimEnd());
    }
    lines.push("");
  }
  // A corner nobody wrote says nothing: only the versions that stand are named.
  const written = corners.filter((corner) => corner.row !== null);
  if (written.length > 0) lines.push(`  ${written.map((corner) => `${corner.name} ${versionLine(corner.row!)}`).join(" · ")}`);
  const rest = FIELDS.length - set.length;
  lines.push(formatHint(set.length === 0 ? `pinecall agent set --help names the ${FIELDS.length} fields` : `${count(rest, "more field")} at the runtime's defaults · pinecall agent set --help names them`));
  return lines;
}

/** What a write changed, as one line per field: the agent, the env, the corner and its version, then `field before → after`. */
export function written(done: CornerWritten): string[] {
  const moved = changes(done.before, done.after, "  ", "\n");
  return [`${done.agent} · ${done.answer.world} · ${done.corner} v${done.version ?? "?"}`, ...(moved === "" ? ["  nothing moved"] : [moved])];
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
    if (turn.min_interruption_ms !== undefined && turn.min_interruption_ms !== null) said.push(`interrupt after ${turn.min_interruption_ms} ms`);
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
  if (field === "silence-timeout" || field === "llm-timeout") {
    const seconds = config[WIRE[field] as "silence_timeout_s"] ?? undefined;
    return seconds === undefined ? undefined : `${seconds} s`;
  }
  if (field === "idle") {
    const idle = config.idle ?? undefined;
    if (idle === undefined) return undefined;
    return `${idle.says.length} line${idle.says.length === 1 ? "" : "s"}${idle.after_s === undefined ? "" : ` · after ${idle.after_s} s`}${idle.times === undefined ? "" : ` · ${idle.times} times`}`;
  }
  if (field === "voicemail") {
    const voicemail = config.voicemail ?? undefined;
    if (voicemail === undefined) return undefined;
    return voicemail.message === undefined || voicemail.message === null ? "hangs up on a machine" : `leaves "${voicemail.message}"`;
  }
  if (field === "stt-fallbacks" || field === "tts-fallbacks") {
    const vendors = config[WIRE[field] as "stt_fallbacks"] ?? undefined;
    return vendors === undefined || vendors.length === 0 ? undefined : vendors.join(" · ");
  }
  if (field === "temperature") {
    const temperature = config.temperature ?? undefined;
    return temperature === undefined ? undefined : String(temperature);
  }
  if (field === "llm-options" || field === "realtime-options" || field === "stt-options" || field === "tts-options" || field === "judge-options") {
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
  const lines = [`${agent} · ${kept.world} · ${kept.holder === "" ? "the org's own corner" : `${kept.holder}'s corner`}`];
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
  if (text === null) return formatNotice(NOTHING_KNOWN(agent, corner));
  return text.replace(/\n$/, "").split("\n");
}

export function knowledgeWritten(done: CornerWritten, text: string): string {
  return `${done.agent} · knowledge ${text.trim() === "" ? "taken out" : `${text.length.toLocaleString("en-US")} chars`} · ${done.corner} v${done.version ?? "?"}`;
}

/** The effective lexicon — or, after a write with `--team`, the team's corner it wrote — then each corner's version. */
export function lexicon(answer: LexiconAnswer, wrote: "yours" | "team" = "yours"): string[] {
  const team = wrote === "team" || answer.yours === null;
  const read = team ? answer.team : answer.yours;
  const lines = [`lexicon · ${answer.world}${wrote === "team" ? " · the team's corner" : answer.yours === null ? "" : " · your corner"}`];
  const said = read?.lexicon.said ?? [];
  const heard = read?.lexicon.heard ?? [];
  if (said.length === 0 && heard.length === 0) lines.push("  nothing set: the voice says every word as it is written");
  else {
    const width = Math.max(0, ...said.map((one) => one.word.length));
    lines.push(...said.map((one, at) => `  ${(at === 0 ? "says" : "").padEnd(5)}  ${one.word.padEnd(width)}  as "${one.spoken}"`));
    if (heard.length > 0) lines.push(`  ${"hears".padEnd(5)}  ${heard.join(" · ")}`);
  }
  // A corner nobody wrote says nothing: only the versions that stand are named.
  const corners: [string, LexiconRow | null][] = [["yours", answer.yours], ["team", answer.team], ["production", answer.production]];
  const written = corners.filter(([, row]) => row !== null);
  if (written.length > 0) lines.push(`  ${written.map(([name, row]) => `${name} ${versionLine(row!)}`).join(" · ")}`);
  if (said.length === 0 && heard.length === 0) lines.push(formatHint('pinecall lexicon add <word> --say "<spoken>" teaches the voice one'));
  return lines;
}

export function lexiconHistory(kept: LexiconHistory): string[] {
  const lines = [`lexicon · ${kept.world} · ${kept.holder === "" ? "the org's own corner" : `${kept.holder}'s corner`}`];
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

/** What a caller hears while a tool runs or the model is slow, and after how many seconds of the agent's quiet. */
export function melody(held: HoldMelody): string[] {
  const plays = held.played === "off" ? "nothing" : held.played === "default" ? "the runtime's melody" : `${held.name ?? "an uploaded file"}${held.seconds === null ? "" : ` · ${held.seconds} s`}, looped`;
  const after = held.played === "off" ? `${held.after_s} s, kept for when a melody plays again` : `${held.after_s} s of the agent's quiet`;
  return [`plays   ${plays}`, `after   ${after}`];
}

/** Every app connected in the env as a table: its id (what `agent stop` takes), its agents, whose, the host, the client, since when. */
export function apps(found: AppProcess[]): string[] {
  if (found.length === 0) return formatNotice(NO_APPS);
  const rows = table(
    ["app", "agents", "held by", "host", "client", "since"],
    found.map((app) => [app.app, app.agents.join(", ") || "—", app.holder === null ? "the org" : (app.holder.name ?? app.holder.holder ?? "—"), app.host ?? "—", app.sdk ?? "—", date(app.connected_at)]),
  );
  const agents = new Set(found.flatMap((app) => app.agents)).size;
  return [...rows, `${count(found.length, "app")} · ${count(agents, "agent")}`, formatHint("pinecall agent stop <app> lets one go")];
}

export function appStopped({ app }: { app: string }): string {
  return `stopped ${app}: its agents are free — a supervisor that restarts it (systemd, pm2) starts it again`;
}

export function killed({ agent, envs, apps }: KilledAgent): string[] {
  return [
    `killed ${agent} in ${envs.join(", ")} · ${count(apps.length, "app")} let go of it and kept their other agents`,
    formatHint("its settings and calls stay", "an app that declares it again, a pinecall start, holds it again"),
  ];
}

/**
 * The voices, one row per voice with every language it speaks: a vendor that lists one voice per
 * language reads as 30 voices, not 240. The name shows only where it is not the id, where each is
 * from only where the vendor says; then how many, and how to hear one.
 */
export function voices(found: ListedVoice[]): string[] {
  if (found.length === 0) return [NO_VOICES];
  const from = (voice: ListedVoice): string => [voice.country, voice.accent].filter((word) => word !== "").join(" ");
  const grouped = new Map<string, { voice: ListedVoice; languages: string[] }>();
  for (const voice of found) {
    const key = [voice.id, voice.name, voice.gender, from(voice)].join("\u0000");
    const one = grouped.get(key) ?? { voice, languages: [] };
    if (!one.languages.includes(voice.language)) one.languages.push(voice.language);
    grouped.set(key, one);
  }
  const rows = [...grouped.values()].sort((one, other) => one.voice.name.localeCompare(other.voice.name) || from(one.voice).localeCompare(from(other.voice)));
  const languages = new Set(found.map((voice) => voice.language));
  const named = rows.some(({ voice }) => voice.name !== voice.id);
  const placed = rows.some(({ voice }) => from(voice) !== "");
  const several = languages.size > 1;
  const headers = ["voice", ...(named ? ["name"] : []), "gender", ...(placed ? ["from"] : []), ...(several ? ["languages"] : [])];
  const lines = table(
    headers,
    rows.map(({ voice, languages: spoken }) => [voice.id, ...(named ? [voice.name] : []), voice.gender, ...(placed ? [from(voice)] : []), ...(several ? [[...spoken].sort().join(" ")] : [])]),
  );
  const spoken = languages.size === 1 ? `in ${[...languages][0]}` : count(languages.size, "language");
  return [...lines, `${count(rows.length, "voice")} · ${spoken}`, formatHint(...(several ? ["--language <tag> keeps one"] : []), "pinecall voices play <id> says a line")];
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

/** Each walk the agent published: its name, its button, its sentences and length, the voice it was recorded in. */
export function walks({ agent, walks }: { agent: string; walks: WalkListed[] }): string[] {
  if (walks.length === 0) return formatNotice(NO_WALKS(agent));
  return table(
    ["walk", "title", "sentences", "length", "voice"],
    walks.map((walk) => [walk.name, walk.title, String(walk.sentences), duration(walk.ms / 1000), walk.voice ?? "—"]),
  );
}

export function walkPlayed(played: WalkPlayed): string {
  return `${played.walk} · ${played.sentences} sentences · ${played.player}`;
}
