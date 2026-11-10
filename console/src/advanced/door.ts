/** Advanced's own doors, beside the settings Configure already reads: what the organization sets for all its agents. */

import { z } from "zod";

import { read, type Credentials } from "@pinecall/core/api";
import type { TuningBody } from "../configure/door";

const WebhookSchema = z.looseObject({ url: z.string(), signed: z.boolean() }).nullable();
const PolicySchema = z.looseObject({
  policy: z.looseObject({
    retention_days: z.number().nullish(),
    calling_hours: z.looseObject({ from: z.number(), until: z.number() }).nullish(),
    consent_everywhere: z.boolean().default(false),
    recording_notice: z.boolean().default(true),
  }),
});

export type Webhook = z.infer<typeof WebhookSchema>;
export type Policy = z.infer<typeof PolicySchema>["policy"];

const WordSchema = z.looseObject({ provider: z.string(), model: z.string() });
const RunsOnSchema = z.looseObject({
  turn: z.looseObject({ min_interruption_words: z.int().nullish(), endpointing_ms: z.int().nullish(), eot_threshold: z.number().nullish(), eager_eot_threshold: z.number().nullish(), min_interruption_ms: z.int().nullish() }).nullish(),
  stt: z.looseObject({ end_of_turn: z.enum(["stt", "livekit", "smart-turn"]).nullish() }).nullish(),
  record: z.boolean().nullish(),
  max_duration_s: z.int().nullish(),
  llm_timeout_s: z.number().nullish(),
  silence_timeout_s: z.int().nullish(),
  idle: z.looseObject({ says: z.array(z.string()), after_s: z.number().optional(), times: z.int().optional() }).nullish(),
  voicemail: z.looseObject({ message: z.string().nullish() }).nullish(),
  stt_fallbacks: z.array(WordSchema).default([]),
  tts_fallbacks: z.array(WordSchema).default([]),
});

const wordOf = (one: { provider: string; model: string }): string => (one.model === "" ? one.provider : `${one.provider}/${one.model}`);

/** What an app's calls run on, its class under the settings, in the settings' own shape; null when nobody holds it, or the key may not read it. */
export async function readRunsOn(credentials: Credentials, agent: string): Promise<TuningBody | null> {
  try {
    const runs = RunsOnSchema.parse(await read(credentials, `/v1/agents/${encodeURIComponent(agent)}/config`));
    const voicemail = runs.voicemail;
    const idle = runs.idle;
    return {
      ...(runs.turn == null ? {} : { turn: { min_interruption_words: runs.turn.min_interruption_words, endpointing_ms: runs.turn.endpointing_ms, eot_threshold: runs.turn.eot_threshold, eager_eot_threshold: runs.turn.eager_eot_threshold, min_interruption_ms: runs.turn.min_interruption_ms } }),
      end_of_turn: runs.stt?.end_of_turn ?? null,
      record: runs.record ?? null,
      max_duration_s: runs.max_duration_s ?? null,
      llm_timeout_s: runs.llm_timeout_s ?? null,
      silence_timeout_s: runs.silence_timeout_s ?? null,
      ...(idle == null ? {} : { idle: { says: idle.says, ...(idle.after_s === undefined ? {} : { after_s: idle.after_s }), ...(idle.times === undefined ? {} : { times: idle.times }) } }),
      ...(voicemail == null ? {} : { voicemail: voicemail.message == null ? {} : { message: voicemail.message } }),
      stt_fallbacks: runs.stt_fallbacks.map(wordOf),
      tts_fallbacks: runs.tts_fallbacks.map(wordOf),
    };
  } catch {
    return null;
  }
}

export async function readWebhook(credentials: Credentials): Promise<Webhook> {
  return WebhookSchema.parse(await read(credentials, "/v1/webhook"));
}

export async function readPolicy(credentials: Credentials): Promise<Policy> {
  return PolicySchema.parse(await read(credentials, "/v1/org/policy")).policy;
}
