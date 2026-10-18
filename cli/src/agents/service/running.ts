/** What an agent runs with: its pipeline as the next call would be built, the processes holding the org's agents, and a vendor's voices. */

import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import type { AppProcess, AppStopped, KilledAgent } from "@pinecall/agents/wire";
import { z } from "zod";

import * as api from "../../api/agents.js";
import type { Context } from "../../context.js";
import { PinecallError, UsageError } from "../../errors.js";
import type { FilePlayer } from "../../kit/player.js";
import { agentNamed } from "./settings.js";

export type { AppProcess, KilledAgent, ListedVoice, PipelineReport, VoiceSaid } from "../../api/agents.js";

/** What `voices` takes: the vendor (the gateway's own when left out), a language, a country. */
export const ListVoicesInput = z.object({
  tts: z.string().min(1).optional(),
  language: z.string().min(1).optional(),
  country: z.string().min(1).optional(),
});
export type ListVoicesInput = z.infer<typeof ListVoicesInput>;

/** What `voices play` and `voice_sample` take: the voice, the words (the gateway's own when left out), the vendor and its model. */
export const SampleVoiceInput = z.object({
  voice: z.string().min(1),
  text: z.string().optional(),
  tts: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  language: z.string().min(1).optional(),
});
export type SampleVoiceInput = z.infer<typeof SampleVoiceInput>;

/** A sample said and written to a file, with how long the vendor took. */
export interface VoiceSampled {
  voice: string;
  tts: string;
  file: string;
  firstAudioMs: number | null;
  totalMs: number | null;
}

/** A sample played on this machine: the player used, or why it could not be, and the file when kept. */
export interface VoicePlayed extends VoiceSampled {
  player: string | null;
  kept: boolean;
}

export async function showPipeline(ctx: Context, agent: string | undefined): Promise<api.PipelineReport> {
  return api.getPipeline(ctx.gateway(), agentNamed(ctx, agent));
}

export async function listApps(ctx: Context): Promise<AppProcess[]> {
  return api.listApps(ctx.gateway());
}

/** The gateway closes the app's socket with the stop code, and the process exits instead of reconnecting. */
export async function stopApp(ctx: Context, app: string): Promise<AppStopped> {
  if (app === "") throw new UsageError("stop takes the app: the first column of `pinecall agent list`");
  return api.stopApp(ctx.gateway(), app);
}

/** The agent let go by every app that holds it in this env, whoever's; the gateway refuses a key that is not an admin's. */
export async function killAgent(ctx: Context, agent: string | undefined): Promise<KilledAgent> {
  return api.killAgent(ctx.gateway(), ctx.slug("kill", { agent }));
}

/** What a vendor whose plugin lists no voices is told, with the vendors that list theirs. */
export function notListed(vendor: string, listing: string[]): string {
  const others = listing.length === 0 ? "no vendor of this gateway lists its voices" : `these list theirs: ${listing.join(", ")} (--tts <vendor>)`;
  return `${vendor} lists no voices: its voice is the vendor's own id, set as it is — ${others}`;
}

/** The vendor's voices in a language, from one country when it is named; a vendor that lists none is a failed check naming the ones that do. */
export async function listVoices(ctx: Context, input: ListVoicesInput): Promise<api.ListedVoice[]> {
  const gw = ctx.gateway();
  const catalogue = await api.getVoiceCatalogue(gw);
  const vendor = input.tts ?? defaultVoiceVendor(catalogue);
  const listing = catalogue.providers.filter((one) => one.voices_listed).map((one) => one.name);
  if (catalogue.providers.some((one) => one.name === vendor) && !listing.includes(vendor)) throw new PinecallError(notListed(vendor, listing));
  const voices = await api.listVoices(gw, vendor, input.language);
  const country = input.country?.toUpperCase();
  return voices.filter((voice) => country === undefined || voice.country === country);
}

/** The words said in the voice through the vendor's own plugin, as a call would, written to `file`. */
export async function sampleVoice(ctx: Context, input: SampleVoiceInput, file: string): Promise<VoiceSampled> {
  const gw = ctx.gateway();
  const tts = input.tts ?? defaultVoiceVendor(await api.getVoiceCatalogue(gw));
  const said = await api.sampleVoice(gw, { tts, voice: input.voice, model: input.model ?? null, language: input.language ?? null, text: input.text ?? null });
  writeFileSync(file, said.wav);
  return { voice: input.voice, tts, file, firstAudioMs: said.firstAudioMs, totalMs: said.totalMs };
}

/** A sample said, played here, and removed unless `save` names where to keep it. */
export async function playVoice(ctx: Context, input: SampleVoiceInput, save: string | undefined, play: FilePlayer): Promise<VoicePlayed> {
  const kept = save === undefined ? null : resolve(save);
  const file = kept ?? join(mkdtempSync(join(tmpdir(), "pinecall-voice-")), "sample.wav");
  const sampled = await sampleVoice(ctx, input, file);
  const played = play(file);
  if ("failed" in played) throw new PinecallError(`${played.failed}: the sample is ${file}`);
  if (kept === null) rmSync(file, { force: true });
  return { ...sampled, player: played.player, kept: kept !== null };
}

/** The gateway's own voice: what an agent that names no vendor speaks with. */
export function defaultVoiceVendor(catalogue: api.VoiceCatalogue): string {
  const vendor = catalogue.defaults["tts"];
  if (vendor === undefined) throw new UsageError("this gateway names no voice of its own: name one with --tts <vendor>");
  return vendor;
}

/** How many tools the agent's holder declared; undefined when the gateway would not say. */
export async function countTools(ctx: Context, agent: string): Promise<number | undefined> {
  try {
    return (await api.getAgentConfig(ctx.gateway(), agent)).tools?.length;
  } catch {
    return undefined;
  }
}
