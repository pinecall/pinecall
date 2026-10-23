/** An agent's settings: the fields, set and cleared as the next version of a corner, their versions, and a corner as a file. */

import type { TuningDiff, TuningHistory } from "@pinecall/agents/wire";
import { z } from "zod";

import * as api from "../../api/agents.js";
import type { Context } from "../../context.js";
import { PinecallError, UsageError } from "../../errors.js";
import { readJsonFile } from "../../kit/json-file.js";
import * as providers from "../../providers/service.js";
import { cornerName, type CornerWritten, cornerWritten, readSettings, rowToStartFrom, sameSettings, type TuningAnswer, type TuningBody, writeCorner } from "./corners.js";

/** Settings fields in display order, as typed on the command line. */
export const FIELDS = [
  "voice", "tts", "tts-model", "tts-builds", "tts-options",
  "stt", "stt-builds", "stt-options", "end-of-turn",
  "llm", "temperature", "llm-builds", "llm-options",
  "realtime", "realtime-options",
  "judge", "judge-builds", "judge-options",
  "language", "greeting", "hangup", "turn", "memory", "record", "max-duration", "knowledge", "bases",
] as const;
export type Field = (typeof FIELDS)[number];

/** Command-line field name to wire field name. */
export const WIRE: Record<Field, keyof TuningBody> = {
  voice: "voice", tts: "tts", "tts-model": "tts_model", "tts-builds": "tts_builds", "tts-options": "tts_options",
  stt: "stt", "stt-builds": "stt_builds", "stt-options": "stt_options", "end-of-turn": "end_of_turn",
  llm: "llm", temperature: "temperature", "llm-builds": "llm_builds", "llm-options": "llm_options",
  realtime: "realtime", "realtime-options": "realtime_options",
  judge: "judge", "judge-builds": "judge_builds", "judge-options": "judge_options",
  language: "language", greeting: "greeting", hangup: "hangup", turn: "turn", memory: "memory", record: "record",
  "max-duration": "max_duration_s", knowledge: "knowledge", bases: "bases",
};

/** What the class calls the setting a field is part of: a field it declares is fixed, and set by it. */
export const DECLARED_AS: Partial<Record<Field, string>> = {
  voice: "voice", tts: "voice", "tts-model": "voice", "tts-builds": "voice", "tts-options": "voice",
  stt: "stt", "stt-builds": "stt", "stt-options": "stt", "end-of-turn": "stt",
  llm: "llm", temperature: "llm", "llm-builds": "llm", "llm-options": "llm",
  realtime: "realtime", "realtime-options": "realtime",
  judge: "judge", "judge-builds": "judge", "judge-options": "judge",
  language: "language", greeting: "greeting", hangup: "hangup", turn: "turn", memory: "memory", record: "record", knowledge: "knowledge", bases: "docs",
};

export const END_OF_TURN = ["stt", "livekit", "smart-turn"] as const;
const LONGEST_MINUTES = 60;
// `improvise` alone opens on the prompt; `improvise:…` with an instruction; anything else is words.
const IMPROVISE = "improvise";

export const NO_LANGUAGE = "--language needs a tag, such as en, es or pt-BR: pinecall agent clear language takes it out";

// The checks a flag passes before anything is read or written, in the CLI's words.
const A_THRESHOLD = "a threshold is a number above 0 and up to 1, such as 0.7";
const fraction = z.number().gt(0, A_THRESHOLD).max(1, A_THRESHOLD);
const ON_OR_OFF = (flag: string): { error: string } => ({ error: `${flag} takes on or off` });
const A_COUNT = (flag: string, of: string): string => `${flag} is a whole number of ${of}, 0 or more`;
const A_DURATION = `--max-duration is minutes, 1 to ${LONGEST_MINUTES}, or off`;

/** What `set` takes, under the CLI's own flag names, so the terminal and the MCP turn either into a version. */
export const SettingsInput = z
  .object({
    voice: z.string(),
    tts: z.string(),
    "tts-model": z.string(),
    stt: z.string(),
    llm: z.string(),
    temperature: z.number().min(0, "--temperature is 0 or more"),
    "llm-builds": z.string(),
    "llm-options": z.record(z.string(), z.unknown()),
    realtime: z.string(),
    "realtime-options": z.record(z.string(), z.unknown()),
    "stt-builds": z.string(),
    "stt-options": z.record(z.string(), z.unknown()),
    "tts-builds": z.string(),
    "tts-options": z.record(z.string(), z.unknown()),
    judge: z.string(),
    "judge-builds": z.string(),
    "judge-options": z.record(z.string(), z.unknown()),
    language: z.string().trim().min(1, NO_LANGUAGE),
    greeting: z.string(),
    "greeting-interruptible": z.enum(["on", "off"], ON_OR_OFF("--greeting-interruptible")),
    "end-of-turn": z.enum(END_OF_TURN, { error: `--end-of-turn takes ${END_OF_TURN.join(", ")}` }),
    hangup: z.string(),
    "endpointing-ms": z.number().int(A_COUNT("--endpointing-ms", "milliseconds")).min(0, A_COUNT("--endpointing-ms", "milliseconds")),
    "min-interruption-words": z.number().int(A_COUNT("--min-interruption-words", "words")).min(0, A_COUNT("--min-interruption-words", "words")),
    "eot-threshold": fraction,
    "eager-eot-threshold": fraction,
    record: z.enum(["on", "off"], ON_OR_OFF("--record")),
    "max-duration": z.union([z.number().int(A_DURATION).min(1, A_DURATION).max(LONGEST_MINUTES, A_DURATION), z.literal("off")], { error: A_DURATION }),
    remember: z.array(z.string()),
    forget: z.array(z.string()),
  })
  .partial();
export type SettingsInput = z.infer<typeof SettingsInput>;

/** What a write of settings carries beside the fields: whose corner and why. */
export const WriteOptions = z.object({
  agent: z.string().min(1).optional(),
  team: z.boolean().default(false),
  note: z.string().optional(),
});
export type WriteOptions = z.infer<typeof WriteOptions>;

/** A pulled settings file: agent, corner, version and the full config. */
export interface Pulled {
  agent: string;
  world: string;
  holder: string;
  version: number;
  config: TuningBody;
}

/** The agent's settings in their three corners, as this key sees them. */
export async function showSettings(ctx: Context, agent: string | undefined): Promise<{ agent: string; answer: TuningAnswer }> {
  const name = agentNamed(ctx, agent);
  return { agent: name, answer: await readSettings(ctx, name) };
}

/** The fields named written as the next version of a corner; the whole set travels, so the rest is carried over. */
export async function setSettings(ctx: Context, input: SettingsInput, options: WriteOptions): Promise<{ agent: string; answer: TuningAnswer }> {
  const name = agentNamed(ctx, options.agent);
  const checked = withModelsNamed(input);
  const written = await writeCorner(ctx, name, options.team, (config) => ({ ...config, ...fieldsOf(checked, config) }), options.note ?? null);
  return { agent: name, answer: written.answer };
}

/** Fields taken out of the corner's own row, so the runtime's default stands again; none named is every one. */
export async function clearSettings(ctx: Context, fields: string[], options: WriteOptions): Promise<{ agent: string; answer: TuningAnswer }> {
  const name = agentNamed(ctx, options.agent);
  const unknown = fields.filter((field) => !(FIELDS as readonly string[]).includes(field));
  if (unknown.length > 0) throw new UsageError(`no field called ${unknown.join(", ")}: ${FIELDS.join(" · ")}`);
  const written = await writeCorner(
    ctx,
    name,
    options.team,
    (standing) => {
      const config: TuningBody = fields.length === 0 ? {} : { ...standing };
      for (const field of fields) delete config[WIRE[field as Field]];
      return config;
    },
    fields.length === 0 ? "cleared" : `cleared ${fields.join(", ")}`,
  );
  return { agent: name, answer: written.answer };
}

export async function settingsHistory(ctx: Context, agent: string | undefined, team: boolean): Promise<{ agent: string; history: TuningHistory }> {
  const name = agentNamed(ctx, agent);
  return { agent: name, history: await api.getSettingsHistory(ctx.gateway(), name, team) };
}

export async function settingsDiff(ctx: Context, agent: string | undefined, against: "team" | "production", team = false): Promise<{ agent: string; against: string; diff: TuningDiff }> {
  const name = agentNamed(ctx, agent);
  return { agent: name, against, diff: await api.getSettingsDiff(ctx.gateway(), name, against, team) };
}

export async function rollbackSettings(ctx: Context, version: number, options: WriteOptions): Promise<{ agent: string; answer: TuningAnswer }> {
  if (!Number.isInteger(version) || version < 1) throw new UsageError("rollback takes the version to bring back: `pinecall agent history` lists them");
  const name = agentNamed(ctx, options.agent);
  return { agent: name, answer: await api.rollbackSettings(ctx.gateway(), name, version, options.team) };
}

/** A corner's config as a file; a machine key has no corner of its own, so it pulls the org's: what CI keeps in the repo. */
export async function pullSettings(ctx: Context, agent: string | undefined, team: boolean): Promise<Pulled> {
  const name = agentNamed(ctx, agent);
  const answer = await readSettings(ctx, name);
  // The corner's own row, what a push sends back to it: a field it never set follows the team's.
  const row = cornerWritten(answer, team, ctx.gateway());
  if (row === null || Object.keys(row.config).length === 0) throw new PinecallError(`nothing set for ${name} in ${cornerName(answer, team, ctx.gateway())} of ${answer.world}`);
  return { agent: name, world: answer.world, holder: row.holder, version: row.version, config: row.config };
}

/** A file sent as the next version; no version guard: CI applies the file as the source of truth. */
export async function pushSettings(ctx: Context, file: string, options: WriteOptions): Promise<CornerWritten & { file: string }> {
  const name = agentNamed(ctx, options.agent);
  const read = readJsonFile<Partial<Pulled>>("the settings file", file);
  const config = read.config ?? (read as TuningBody);
  const gw = ctx.gateway();
  const standing = await readSettings(ctx, name);
  if (sameSettings(config, cornerWritten(standing, options.team, gw)?.config ?? {})) throw new UsageError(`nothing changes in ${cornerName(standing, options.team, gw)}: it already reads as ${file}`);
  const answer = await api.putSettings(gw, name, { config, if_version: null, note: `pushed from ${file}`, team: options.team });
  return { agent: name, corner: cornerName(answer, options.team, gw), version: cornerWritten(answer, options.team, gw)?.version ?? null, answer, file };
}

/** What the agent knows by heart in a corner: the text, or null when nothing is set there. */
export async function readKnowledge(ctx: Context, agent: string | undefined, team: boolean): Promise<{ agent: string; corner: string; knowledge: string | null }> {
  const name = agentNamed(ctx, agent);
  const gw = ctx.gateway();
  const answer = await readSettings(ctx, name);
  return { agent: name, corner: cornerName(answer, team, gw), knowledge: rowToStartFrom(answer, team)?.config.knowledge ?? null };
}

/** The text kept as what the agent knows by heart, the next version of the corner; empty takes it out. */
export async function writeKnowledge(ctx: Context, text: string, options: WriteOptions): Promise<CornerWritten> {
  const name = agentNamed(ctx, options.agent);
  // An empty file removes the field (the gateway refuses a blank value), so the default applies again.
  return writeCorner(
    ctx,
    name,
    options.team,
    (config) => {
      const { knowledge: _was, ...rest } = config;
      return text.trim() === "" ? rest : { ...rest, knowledge: text };
    },
    options.note ?? "knowledge",
  );
}

/** The opening a `greeting` names: words, or the model's own with or without an instruction. */
export function openingOf(said: string): { say: string } | { reply: string } {
  if (said === IMPROVISE) return { reply: "" };
  if (said.startsWith(`${IMPROVISE}:`)) return { reply: said.slice(IMPROVISE.length + 1).trim() };
  return { say: said };
}

/** The agent a settings verb acts on: the one named, or the project's only one. */
export function agentNamed(ctx: Context, agent: string | undefined): string {
  return ctx.slug("agent", { agent });
}

// A model knob reads four ways; a name that means no model at all is refused rather than written.
function withModelsNamed(input: SettingsInput): SettingsInput {
  const checked = { ...input };
  for (const field of ["llm", "judge"] as const) {
    const said = input[field];
    if (said === undefined) continue;
    const named = providers.modelFieldOf(said);
    if (named === undefined) throw new UsageError(providers.NOT_A_MODEL(said, `--${field}`));
    checked[field] = named;
  }
  return checked;
}

/** The fields this input sets, under wire names, merged over the current row where nested. */
export function fieldsOf(input: SettingsInput, standing: TuningBody): Partial<TuningBody> {
  const wanted: Partial<TuningBody> = {};
  for (const field of ["voice", "tts", "tts-model", "stt", "llm", "llm-builds", "realtime", "stt-builds", "tts-builds", "judge", "judge-builds", "language"] as const) {
    const value = input[field];
    if (typeof value === "string") (wanted as Record<string, unknown>)[WIRE[field]] = value;
  }
  if (input.temperature !== undefined) wanted.temperature = input.temperature;
  for (const stage of ["llm", "realtime", "stt", "tts", "judge"] as const) {
    const options = input[`${stage}-options`];
    if (options !== undefined) wanted[`${stage}_options`] = options;
  }
  if (input.greeting !== undefined) wanted.greeting = openingOf(input.greeting);
  const interruptible = input["greeting-interruptible"];
  if (interruptible !== undefined) wanted.greeting = { ...(wanted.greeting ?? standing.greeting ?? {}), allow_interruptions: interruptible === "on" };
  // `any`: the model ends the call whenever it judges it done.
  if (input.hangup !== undefined) wanted.hangup = { when: input.hangup === "any" ? "" : input.hangup };
  if (input["end-of-turn"] !== undefined) wanted.end_of_turn = input["end-of-turn"];
  const endpointing = input["endpointing-ms"];
  const words = input["min-interruption-words"];
  const sure = input["eot-threshold"];
  const eager = input["eager-eot-threshold"];
  if ([endpointing, words, sure, eager].some((one) => one !== undefined)) {
    wanted.turn = { ...(standing.turn ?? {}) };
    if (endpointing !== undefined) wanted.turn.endpointing_ms = endpointing;
    if (words !== undefined) wanted.turn.min_interruption_words = words;
    if (sure !== undefined) wanted.turn.eot_threshold = sure;
    if (eager !== undefined) wanted.turn.eager_eot_threshold = eager;
  }
  if (input.record !== undefined) wanted.record = input.record === "on";
  // Minutes, or `off`; sent as seconds, with 0 meaning no limit.
  if (input["max-duration"] !== undefined) wanted.max_duration_s = input["max-duration"] === "off" ? 0 : input["max-duration"] * 60;
  if (input.remember !== undefined || input.forget !== undefined) {
    wanted.memory = { remember: input.remember ?? standing.memory?.remember ?? [], forget: input.forget ?? standing.memory?.forget ?? [] };
  }
  return wanted;
}
