/** Configure's doors: the agent's settings in its corners, what its next call runs on and how its calls measured, voices, and its lexicon. */

import { z } from "zod";

import { answered, doorUrl, headersFor, post, put, read, type Credentials } from "@pinecall/core/api";
import { type ListedVoice, VoicesListedSchema } from "@pinecall/core/wire/rest-evals";
import { type LexiconAnswer, LexiconAnswerSchema, type LexiconBody, type TuningAnswer, TuningAnswerSchema, type TuningBody } from "@pinecall/core/wire/rest-org";

export type { LexiconAnswer, LexiconBody, ListedVoice, TuningAnswer, TuningBody };

const StageSchema = z.object({ vendor: z.string(), model: z.string().nullable(), voice_id: z.string().nullable(), language: z.string().nullable() });
const ProviderSchema = z.looseObject({ name: z.string(), does: z.array(z.string()), ready: z.boolean(), voices_listed: z.boolean(), availability: z.string().optional(), broken: z.string().nullish() });

const PluginOptionSchema = z.object({
  name: z.string(),
  inside: z.string().nullable(),
  kind: z.enum(["text", "number", "integer", "boolean", "choice", "list", "json"]),
  choices: z.array(z.string()),
  open: z.boolean(),
  default: z.unknown(),
  required: z.boolean(),
});
const PluginOptionsSchema = z.object({ vendor: z.string(), modality: z.string(), builds: z.string(), options: z.array(PluginOptionSchema) });
export type PluginOption = z.infer<typeof PluginOptionSchema>;
export type PluginOptions = z.infer<typeof PluginOptionsSchema>;

const ModelPriceSchema = z.object({ input: z.number().nullish(), output: z.number().nullish(), characters: z.number().nullish(), audio_seconds: z.number().nullish(), minutes: z.number().nullish() });
const ModelChoiceSchema = z.object({ model: z.string(), name: z.string(), recommended: z.boolean(), available: z.boolean(), price: ModelPriceSchema.nullish() });
export type ModelChoice = z.infer<typeof ModelChoiceSchema>;

const ReportSchema = z.looseObject({
  hears: StageSchema,
  decides: StageSchema,
  speaks: StageSchema,
  talks: StageSchema.nullish(),
  greeting: z.looseObject({ say: z.string().nullish(), reply: z.string().nullish() }).nullish(),
  providers: z.array(ProviderSchema),
  defaults: z.record(z.string(), z.string()),
  models: z.record(z.string(), z.array(z.string())),
  // Every model the row offers, the recommended first, each saying whether this org may run it; a runtime before it answers none.
  choices: z.record(z.string(), z.array(ModelChoiceSchema)).default({}),
  runs: z.record(z.string(), z.string()),
  voice_defaults: z.record(z.string(), z.string()).default({}),
  calls: z.number(),
  medians: z.array(z.object({ name: z.string(), seconds: z.number(), turns: z.number() })),
});

export type Report = z.infer<typeof ReportSchema>;
export type Provider = Report["providers"][number];
export type Stage = z.infer<typeof StageSchema>;

const ParamSchema = z.object({
  name: z.string(),
  type: z.enum(["string", "number", "integer", "boolean"]),
  description: z.string(),
  required: z.boolean(),
  enum: z.array(z.string()).nullish(),
});
const FixedFieldSchema = z.object({ name: z.string(), value: z.union([z.string(), z.number(), z.boolean()]) });
const HttpToolSchema = z.looseObject({
  name: z.string(),
  description: z.string(),
  method: z.enum(["GET", "POST", "PUT", "PATCH", "DELETE"]),
  url: z.string(),
  headers: z.array(z.object({ name: z.string(), value: z.string() })),
  params: z.array(ParamSchema),
  fixed: z.array(FixedFieldSchema).default([]),
  announce: z.string().nullish(),
  delayed: z.string().nullish(),
  delayed_after_s: z.number().default(5),
  failed: z.string().nullish(),
  timeout_s: z.number(),
});
export type HttpTool = z.infer<typeof HttpToolSchema>;
export type Param = z.infer<typeof ParamSchema>;
export type FixedField = z.infer<typeof FixedFieldSchema>;

const TriedSchema = z.object({ status: z.number().int().nullable(), body: z.unknown(), error: z.string().nullable(), duration_ms: z.number() });
export type Tried = z.infer<typeof TriedSchema>;

// The definition goes back whole on a save, so what this page does not draw is kept as it was read.
const StudioAgentSchema = z.looseObject({
  release: z.number().int(),
  definition: z.looseObject({ instructions: z.string(), greeting: z.looseObject({ say: z.string().nullish(), reply: z.string().nullish() }).nullish(), tools: z.array(HttpToolSchema).default([]) }),
});
export type StudioAgent = z.infer<typeof StudioAgentSchema>;

const studioOf = (agent: string): string => `/v1/studio/agents/${encodeURIComponent(agent)}`;

export async function readStudioAgent(credentials: Credentials, agent: string): Promise<StudioAgent> {
  return StudioAgentSchema.parse(await read(credentials, studioOf(agent)));
}

export async function saveStudioAgent(credentials: Credentials, agent: string, definition: StudioAgent["definition"], basedOn: number): Promise<StudioAgent> {
  return StudioAgentSchema.parse(await put(credentials, studioOf(agent), { definition, based_on: basedOn }));
}

/** One tool's real request sent once, with the definition as the editor holds it. */
export async function tryTool(credentials: Credentials, agent: string, tool: string, args: Record<string, unknown>, definition: StudioAgent["definition"]): Promise<Tried> {
  return TriedSchema.parse(await post(credentials, `${studioOf(agent)}/try`, { tool, arguments: args, definition }));
}

const settingsOf = (agent: string): string => `/v1/agents/${encodeURIComponent(agent)}/settings`;
const lexiconOf = (agent: string): string => `/v1/agents/${encodeURIComponent(agent)}/lexicon`;

export async function readSettings(credentials: Credentials, agent: string): Promise<TuningAnswer> {
  return TuningAnswerSchema.parse(await read(credentials, settingsOf(agent)));
}

export async function setSettings(credentials: Credentials, agent: string, body: { config: TuningBody; if_version: number | null; note: string | null; team: boolean }): Promise<TuningAnswer> {
  return TuningAnswerSchema.parse(await put(credentials, settingsOf(agent), body));
}

export async function readReport(credentials: Credentials, agent: string): Promise<Report> {
  return ReportSchema.parse(await read(credentials, `/v1/agents/${encodeURIComponent(agent)}/pipeline`));
}

/** The org's own key for a vendor, kept once the vendor took it on one small job; its calls run on it from the next one. */
export async function keepProviderKey(credentials: Credentials, vendor: string, key: string): Promise<void> {
  await put(credentials, `/v1/provider-keys/${encodeURIComponent(vendor)}`, { key });
}

/** What a vendor's plugin takes for a stage, read off its constructor: the form the stage's dialog draws. */
export async function readOptions(credentials: Credentials, vendor: string, modality: "stt" | "llm" | "tts", builds: string | null): Promise<PluginOptions> {
  return PluginOptionsSchema.parse(await read(credentials, `/v1/providers/${encodeURIComponent(vendor)}/options`, builds === null ? { modality } : { modality, builds }));
}

export async function readVoices(credentials: Credentials, tts: string, language: string | null): Promise<ListedVoice[]> {
  return VoicesListedSchema.parse(await read(credentials, "/v1/voices", language === null ? { tts } : { tts, language })).voices;
}

/** One sentence in that voice, as a blob URL the caller revokes: an audio tag cannot send the key. */
export async function sampleOf(credentials: Credentials, asked: { tts: string; voice: string; model: string | null; language: string | null; text: string | null }): Promise<string> {
  const answer = await fetch(doorUrl(credentials, "/v1/voices/sample"), { method: "POST", headers: { ...headersFor(credentials), "content-type": "application/json" }, body: JSON.stringify(asked) });
  if (!answer.ok) await answered(answer);
  return URL.createObjectURL(await answer.blob());
}

export async function readLexicon(credentials: Credentials, agent: string): Promise<LexiconAnswer> {
  return LexiconAnswerSchema.parse(await read(credentials, lexiconOf(agent)));
}

export async function setLexicon(credentials: Credentials, agent: string, lexicon: LexiconBody, ifVersion: number | null, team: boolean): Promise<LexiconAnswer> {
  return LexiconAnswerSchema.parse(await put(credentials, lexiconOf(agent), { lexicon, if_version: ifVersion, note: null, team }));
}
