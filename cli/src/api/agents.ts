/** The agents endpoints: an agent's settings and their versions, its lexicon, its pipeline, the apps holding it, a vendor's voices, its walks. */

import {
  type AppList,
  type AppProcess,
  type AppStopped,
  type KilledAgent,
  type LexiconAnswer,
  type LexiconBody,
  type LexiconHistory,
  type TuningAnswer,
  type TuningBody,
  type TuningDiff,
  type TuningHistory,
  type VoiceSample,
  VoicesListedSchema,
} from "@pinecall/agents/wire";
import { z } from "zod";

export type { AppProcess, AppStopped, KilledAgent, LexiconAnswer, LexiconBody, LexiconHistory, TuningAnswer, TuningBody, TuningDiff, TuningHistory, VoiceSample } from "@pinecall/agents/wire";

import { GatewayError } from "../errors.js";
import { seg, type GatewayClient } from "./client.js";

/** `PUT /v1/agents/{slug}/settings`: the whole set, guarded by the version it was read at (null: no guard). */
export interface SettingsWrite {
  config: TuningBody;
  if_version: number | null;
  note: string | null;
  team: boolean;
}

/** `PUT /v1/agents/{slug}/lexicon`: the whole lexicon, guarded by the version it was read at. */
export interface LexiconWrite {
  lexicon: LexiconBody;
  if_version: number;
  note: string | null;
  team: boolean;
}

/** One stage of the pipeline: its vendor, its model and its one knob worth showing. */
export interface PipelineStage {
  vendor: string;
  model: string | null;
  voice_id: string | null;
  language: string | null;
}

/** A median over the agent's recent calls, named as LiveKit names the metric. */
export interface PipelineMedian {
  name: string;
  seconds: number;
  turns: number;
}

/** `GET /v1/agents/{slug}/pipeline`: the three legs as the next call would be built. */
export interface PipelineReport {
  agent: string;
  hears: PipelineStage;
  decides: PipelineStage;
  speaks: PipelineStage;
  greeting: { say: string | null; reply: string | null } | null;
  voices: string[];
  calls: number;
  medians: PipelineMedian[];
  unavailable_reasons: Record<string, string>;
}

/** The catalogue as the voices read it: which vendor lists its voices, and the gateway's own vendor per stage. */
export interface VoiceCatalogue {
  providers: { name: string; voices_listed: boolean }[];
  defaults: Record<string, string>;
}

/** One voice of a vendor, as `GET /v1/voices` lists it. */
export type ListedVoice = z.infer<typeof VoicesListedSchema>["voices"][number];

/** `POST /v1/voices/sample`: the WAV itself and the gateway's Server-Timing durations, in milliseconds. */
export interface VoiceSaid {
  wav: Uint8Array;
  firstAudioMs: number | null;
  totalMs: number | null;
}

const settingsOf = (agent: string): string => `/v1/agents/${seg(agent)}/settings`;
const lexiconOf = (agent: string): string => `/v1/agents/${seg(agent)}/lexicon`;

export function getSettings(gw: GatewayClient, agent: string): Promise<TuningAnswer> {
  return gw.get<TuningAnswer>(settingsOf(agent));
}

export function putSettings(gw: GatewayClient, agent: string, body: SettingsWrite): Promise<TuningAnswer> {
  return gw.put<TuningAnswer>(settingsOf(agent), body);
}

export function getSettingsHistory(gw: GatewayClient, agent: string, team: boolean): Promise<TuningHistory> {
  return gw.get<TuningHistory>(`${settingsOf(agent)}/history`, { team });
}

export function getSettingsDiff(gw: GatewayClient, agent: string, against: "team" | "production", team = false): Promise<TuningDiff> {
  return gw.get<TuningDiff>(`${settingsOf(agent)}/diff`, team ? { against, team: "true" } : { against });
}

export function rollbackSettings(gw: GatewayClient, agent: string, version: number, team: boolean): Promise<TuningAnswer> {
  return gw.post<TuningAnswer>(`${settingsOf(agent)}/rollback`, { version, team });
}

export function getLexicon(gw: GatewayClient, agent: string): Promise<LexiconAnswer> {
  return gw.get<LexiconAnswer>(lexiconOf(agent));
}

export function putLexicon(gw: GatewayClient, agent: string, body: LexiconWrite): Promise<LexiconAnswer> {
  return gw.put<LexiconAnswer>(lexiconOf(agent), body);
}

export function getLexiconHistory(gw: GatewayClient, agent: string, team: boolean): Promise<LexiconHistory> {
  return gw.get<LexiconHistory>(`${lexiconOf(agent)}/history`, { team });
}

export function getPipeline(gw: GatewayClient, agent: string): Promise<PipelineReport> {
  return gw.get<PipelineReport>(`/v1/agents/${seg(agent)}/pipeline`);
}

/** `GET /v1/agents/{slug}/pipeline/hold-audio`: what a caller hears while a tool runs, and after how many seconds of quiet. */
export interface HoldMelody {
  played: "default" | "off" | "custom";
  sha256: string | null;
  seconds: number | null;
  name: string | null;
  after_s: number;
}

function melodyOf(agent: string): string {
  return `/v1/agents/${seg(agent)}/pipeline/hold-audio`;
}

export function getMelody(gw: GatewayClient, agent: string): Promise<HoldMelody> {
  return gw.get<HoldMelody>(melodyOf(agent));
}

/** The file as it is, no multipart: the gateway tells the format by its first bytes and converts it once. */
export function uploadMelody(gw: GatewayClient, agent: string, audio: Buffer, name: string): Promise<HoldMelody> {
  return gw.request<HoldMelody>(melodyOf(agent), { method: "PUT", body: audio, query: { name } });
}

export function chooseMelody(gw: GatewayClient, agent: string, played: "default" | "off"): Promise<HoldMelody> {
  return gw.put<HoldMelody>(`${melodyOf(agent)}/played`, { played });
}

/** Seconds of quiet before the melody starts; null is the runtime's own wait. */
export function waitBeforeMelody(gw: GatewayClient, agent: string, after_s: number | null): Promise<HoldMelody> {
  return gw.put<HoldMelody>(`${melodyOf(agent)}/after`, { after_s });
}

export async function listApps(gw: GatewayClient): Promise<AppProcess[]> {
  return (await gw.get<AppList>("/v1/apps")).apps;
}

export function stopApp(gw: GatewayClient, app: string): Promise<AppStopped> {
  return gw.post<AppStopped>(`/v1/apps/${seg(app)}/stop`);
}

/** An admin's: every app holding the agent in the env lets go of it, and keeps its other agents. */
export function killAgent(gw: GatewayClient, agent: string): Promise<KilledAgent> {
  return gw.post<KilledAgent>(`/v1/agents/${seg(agent)}/kill`);
}

export function getVoiceCatalogue(gw: GatewayClient): Promise<VoiceCatalogue> {
  return gw.get<VoiceCatalogue>("/v1/providers");
}

/** A vendor's voices in a language; the answer is checked, so a non-list 200 (a proxy page) fails instead of reading as empty. */
export async function listVoices(gw: GatewayClient, tts: string, language: string | undefined): Promise<ListedVoice[]> {
  return VoicesListedSchema.parse(await gw.get<unknown>("/v1/voices", { tts, language })).voices;
}

/** The words said in the voice through the vendor's own plugin, as a call would; the body is the WAV, not JSON. */
export async function sampleVoice(gw: GatewayClient, body: VoiceSample): Promise<VoiceSaid> {
  const answered = await gw.fetch("/v1/voices/sample", { method: "POST", body });
  const timing = answered.headers.get("server-timing") ?? "";
  return {
    wav: new Uint8Array(await answered.arrayBuffer()),
    firstAudioMs: durationOf(timing, "first-audio"),
    totalMs: durationOf(timing, "total"),
  };
}

/** A metric's `dur` in a Server-Timing header, or null when the gateway sent none. */
export function durationOf(header: string, metric: "first-audio" | "total"): number | null {
  const found = new RegExp(`(?:^|,)\\s*${metric};dur=([0-9.]+)`).exec(header);
  return found === null ? null : Number(found[1]);
}

/** `GET /v1/agents/{slug}/config`: what the holder of the agent declared — its tools among it. */
export function getAgentConfig(gw: GatewayClient, agent: string): Promise<{ tools?: unknown[] }> {
  return gw.get<{ tools?: unknown[] }>(`/v1/agents/${seg(agent)}/config`);
}

/** A walk an agent published for its pages (a tutor's macro, recorded in its voice): what the CLI lists and plays of it. */
export interface PublishedWalk {
  name: string;
  title: string;
  voice: string | null;
  steps: { say: string; audio: string; durationMs: number }[];
}

/** `GET /v1/agents/{slug}/public/walks?env=`: the walks the agent published in this env, read with no key; none while it published none. */
export async function getWalks(gw: GatewayClient, agent: string): Promise<PublishedWalk[]> {
  try {
    return walksIn(await gw.get<unknown>(`/v1/agents/${seg(agent)}/public/walks`, { env: gw.env }));
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === 404) return [];
    throw failed;
  }
}

/** A recorded line's MP3, by the URL its walk names: the gateway's own, read with no key. */
export async function getLineAudio(gw: GatewayClient, url: string): Promise<Uint8Array> {
  return new Uint8Array(await (await gw.fetch(new URL(url).pathname)).arrayBuffer());
}

// The document is the app's, read as any page reads it: a walk that is not one is left out, and
// fields the CLI does not show (the words' times, the beats) are left to the page.
const PublishedWalkSchema = z.looseObject({
  name: z.string(),
  title: z.string().optional(),
  voice: z.string().optional(),
  steps: z.array(z.looseObject({ say: z.string(), audio: z.url(), durationMs: z.number() })).min(1),
});

function walksIn(published: unknown): PublishedWalk[] {
  const listed = z.looseObject({ walks: z.array(z.unknown()) }).safeParse(published);
  if (!listed.success) return [];
  return listed.data.walks.flatMap((one) => {
    const walk = PublishedWalkSchema.safeParse(one);
    if (!walk.success) return [];
    const { name, title, voice, steps } = walk.data;
    return [{ name, title: title ?? name, voice: voice ?? null, steps: steps.map(({ say, audio, durationMs }) => ({ say, audio, durationMs })) }];
  });
}
