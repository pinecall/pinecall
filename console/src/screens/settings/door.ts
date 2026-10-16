/** Settings API: read the three corners, set, list history, roll back. */

import { type TuningAnswer, TuningAnswerSchema, type TuningBody, type TuningHistory, TuningHistorySchema, type TuningRow } from "@pinecall/core/wire/rest-org";

import { post, put, read, type Credentials } from "@pinecall/core/api";

function door(agent: string): string {
  return `/v1/agents/${encodeURIComponent(agent)}/settings`;
}

/** Newest config of each corner visible to this key. */
export async function readSettings(credentials: Credentials, agent: string): Promise<TuningAnswer> {
  return TuningAnswerSchema.parse(await read(credentials, door(agent)));
}

/** Set request: full config, base version, reason and target corner. */
export interface Set {
  config: TuningBody;
  if_version: number | null;
  note: string | null;
  team: boolean;
}

/** Save a full config as the corner's next version; returns the three corners. */
export async function setSettings(credentials: Credentials, agent: string, body: Set): Promise<TuningAnswer> {
  return TuningAnswerSchema.parse(await put(credentials, door(agent), body));
}

/** A corner's versions, newest first. */
export async function readHistory(credentials: Credentials, agent: string, team: boolean): Promise<TuningHistory> {
  return TuningHistorySchema.parse(await read(credentials, `${door(agent)}/history`, { team: String(team) }));
}

/** Roll back by re-saving an old version as the next one. */
export async function rollbackTo(credentials: Credentials, agent: string, version: number, team: boolean): Promise<TuningAnswer> {
  return TuningAnswerSchema.parse(await post(credentials, `${door(agent)}/rollback`, { version, team }));
}

/** Displayed fields, in order, with their labels. */
export const FIELDS = ["voice", "tts", "tts_model", "stt", "language", "llm", "greeting", "hangup", "turn", "memory", "record", "max_duration_s", "knowledge", "bases"] as const;
export type Field = (typeof FIELDS)[number];

export const LABEL: Record<Field, string> = {
  voice: "Voice",
  tts: "Voice vendor",
  tts_model: "Voice model",
  stt: "STT",
  language: "Language",
  llm: "LLM",
  greeting: "Opening",
  hangup: "Hang up when",
  turn: "Turn",
  memory: "Memory",
  record: "Recording",
  max_duration_s: "Longest voice call",
  knowledge: "Knowledge",
  bases: "Bases",
};

/** One config field as display text; undefined when unset. */
export function shown(config: TuningBody, field: Field): string | undefined {
  if (field === "greeting") {
    const greeting = config.greeting ?? undefined;
    if (greeting === undefined) return undefined;
    const say = greeting.say ?? undefined;
    return say !== undefined ? `"${say}"` : `reply: ${greeting.reply ?? ""}`;
  }
  if (field === "hangup") {
    const hangup = config.hangup ?? undefined;
    return hangup === undefined ? undefined : hangup.when ? `when ${hangup.when}` : "may hang up";
  }
  if (field === "turn") {
    const turn = config.turn ?? undefined;
    if (turn === undefined) return undefined;
    const said: string[] = [];
    if (typeof turn.endpointing_ms === "number") said.push(`endpointing ${turn.endpointing_ms} ms`);
    if (typeof turn.min_interruption_words === "number") said.push(`interrupt at ${turn.min_interruption_words} words`);
    return said.join(" · ");
  }
  if (field === "memory") {
    const memory = config.memory ?? undefined;
    return memory === undefined ? undefined : `remember ${memory.remember?.length ?? 0} · forget ${memory.forget?.length ?? 0}`;
  }
  // Explicit false is shown: unset falls through, false disables recording.
  if (field === "record") {
    const records = config.record ?? undefined;
    return records === undefined ? undefined : records ? "keeps the audio" : "keeps none";
  }
  // Zero means no limit, so check it before "not set".
  if (field === "max_duration_s") {
    const seconds = config.max_duration_s ?? undefined;
    return seconds === undefined ? undefined : seconds === 0 ? "no limit" : `${seconds / 60} min`;
  }
  if (field === "knowledge") {
    const text = config.knowledge ?? undefined;
    return text === undefined ? undefined : `${text.length.toLocaleString("en-US")} chars`;
  }
  if (field === "bases") {
    const bases = config.bases ?? undefined;
    return bases === undefined || bases.length === 0 ? undefined : bases.map((one) => `${one.base}${typeof one.k === "number" ? ` (k ${one.k})` : ""}`).join(" · ");
  }
  const value = config[field];
  return typeof value === "string" ? value : undefined;
}

/** Fields that differ between two configs, as `field before → after`. */
export function changes(before: TuningBody, after: TuningBody): string[] {
  const said: string[] = [];
  for (const field of FIELDS) {
    const was = shown(before, field);
    const is = shown(after, field);
    if (was !== is) said.push(`${LABEL[field]} ${was ?? "—"} → ${is ?? "—"}`);
  }
  return said;
}

/** Corner the form edits: the person's own when it has a row, else the team's. */
export function edited(answer: TuningAnswer, team: boolean): TuningRow | null {
  return team ? answer.team : answer.yours;
}
