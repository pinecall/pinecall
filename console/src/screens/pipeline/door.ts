/** Schemas for `GET /v1/agents/{slug}/pipeline`, and the hold audio doors. */

import { z } from "zod";

import { answered, doorUrl, headersFor, put, read, type Credentials } from "@pinecall/core/api";
import { ProviderSchema } from "../../lib/catalogue";
import { MEDIANS } from "@pinecall/core/metrics";

// Console-only shapes: the wire describes calls, not this screen.
/** One stage: vendor, model and its main setting. */
export const StageSchema = z.object({
  vendor: z.string(),
  model: z.string().nullable(),
  voice_id: z.string().nullable(),
  language: z.string().nullable(),
});
export type Stage = z.infer<typeof StageSchema>;

// The names are the runtime's MEDIANS; `talk_share` is a share from 0 to 1 that still rides `seconds`.
/** A median over recent calls: the measure's name, its value, and how many turns gave it. */
export const MeasuredSchema = z.object({
  name: z.enum(MEDIANS),
  seconds: z.number(),
  turns: z.int(),
});
export type Measured = z.infer<typeof MeasuredSchema>;

/** How the agent opens a call: exactly one of the two verbs. */
export const GreetingSchema = z.object({
  say: z.string().nullable(),
  reply: z.string().nullable(),
  allow_interruptions: z.boolean().nullable(),
});
export type Greeting = z.infer<typeof GreetingSchema>;

export const ReportSchema = z.object({
  agent: z.string(),
  hears: StageSchema,
  decides: StageSchema,
  speaks: StageSchema,
  greeting: GreetingSchema.nullable(),
  // Allowed voices, from the runtime's table; the console keeps no list of its own.
  voices: z.array(z.string()),
  // Same rows as GET /v1/providers, so both screens agree.
  providers: z.array(ProviderSchema),
  // Default vendor per stage, and curated models per "<modality>/<vendor>" (default first).
  defaults: z.record(z.string(), z.string()),
  models: z.record(z.string(), z.array(z.string())),
  calls: z.int(),
  medians: z.array(MeasuredSchema),
  unavailable_reasons: z.record(z.string(), z.string()),
});
export type Report = z.infer<typeof ReportSchema>;

/** The agent's current pipeline. */
export async function readPipeline(credentials: Credentials, agent: string): Promise<Report> {
  return ReportSchema.parse(await read(credentials, door(agent)));
}

function door(agent: string): string {
  return `/v1/agents/${encodeURIComponent(agent)}/pipeline`;
}

// Separate doors, not a settings field, so a whole-settings PUT cannot clear it.
/** Audio played while a tool runs: the default melody, none, or an uploaded file. */
export const HoldAudioSchema = z.object({
  played: z.enum(["default", "off", "custom"]),
  name: z.string().nullable(),
  seconds: z.number().nullable(),
  sha256: z.string().nullable(),
});
export type HoldAudio = z.infer<typeof HoldAudioSchema>;

export async function readHoldAudio(credentials: Credentials, agent: string): Promise<HoldAudio> {
  return HoldAudioSchema.parse(await read(credentials, `${door(agent)}/hold-audio`));
}

// Raw bytes as the body, no multipart; the gateway decodes anything PyAV reads.
/** Upload a hold audio file; resolves to what the gateway stored. */
export async function uploadHoldAudio(credentials: Credentials, agent: string, file: File): Promise<HoldAudio> {
  const answer = await fetch(doorUrl(credentials, `${door(agent)}/hold-audio`, { name: file.name }), {
    method: "PUT",
    headers: { ...headersFor(credentials), "content-type": file.type || "application/octet-stream" },
    body: file,
  });
  return HoldAudioSchema.parse(await answered(answer));
}

/** Switch to the default melody or to none. */
export async function chooseHoldAudio(credentials: Credentials, agent: string, played: "default" | "off"): Promise<HoldAudio> {
  return HoldAudioSchema.parse(await put(credentials, `${door(agent)}/hold-audio/played`, { played }));
}

// <audio src> cannot send an auth header and keys never go in URLs, so fetch and use a blob URL.
/** Blob URL of the hold audio; the caller must revoke it. */
export async function holdAudioBlob(credentials: Credentials, agent: string): Promise<string> {
  const answer = await fetch(doorUrl(credentials, `${door(agent)}/hold-audio/audio`), { headers: headersFor(credentials) });
  if (!answer.ok) await answered(answer);
  return URL.createObjectURL(await answer.blob());
}
