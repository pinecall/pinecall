/** Configure's doors: the agent's settings in its corners, what its next call runs on and how its calls measured, voices, and its lexicon. */

import { z } from "zod";

import { answered, doorUrl, headersFor, post, put, read, type Credentials } from "@pinecall/core/api";
import { type ListedVoice, VoicesListedSchema } from "@pinecall/core/wire/rest-evals";
import { type LexiconAnswer, LexiconAnswerSchema, type LexiconBody, type TuningAnswer, TuningAnswerSchema, type TuningBody } from "@pinecall/core/wire/rest-org";

export type { LexiconAnswer, LexiconBody, ListedVoice, TuningAnswer, TuningBody };

// `languages`: what the ears listen for and the voice is asked to speak; a runtime before it answers none.
const StageSchema = z.object({ vendor: z.string(), model: z.string().nullable(), voice_id: z.string().nullable(), language: z.string().nullable(), languages: z.array(z.string()).default([]) });
const SuitedSchema = z.object({ vendor: z.string(), model: z.string().nullable(), refused: z.string().nullish() });
export type Suited = z.infer<typeof SuitedSchema>;
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
  // By stage, why it runs but not well: ears that do not hear the agent's languages, a voice that does not speak them; a runtime before it answers none.
  warnings: z.record(z.string(), z.string()).default({}),
  // The languages its callers speak, the main one first, and by stage the runtime's own models that take them all.
  languages: z.array(z.string()).default([]),
  suited: z.record(z.string(), z.array(SuitedSchema)).default({}),
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

// An agent's own words for a channel; one it leaves out is told Pinecall's.
const ChannelRulesSchema = z.object({ voice: z.string().nullish(), chat: z.string().nullish(), whatsapp: z.string().nullish(), sms: z.string().nullish(), email: z.string().nullish(), messenger: z.string().nullish(), instagram: z.string().nullish() });
export type ChannelRules = z.infer<typeof ChannelRulesSchema>;

// The definition goes back whole on a save, so what this page does not draw is kept as it was read.
const StudioAgentSchema = z.looseObject({
  release: z.number().int(),
  definition: z.looseObject({ instructions: z.string(), greeting: z.looseObject({ say: z.string().nullish(), reply: z.string().nullish() }).nullish(), tools: z.array(HttpToolSchema).default([]), channel_rules: ChannelRulesSchema.nullish() }),
});
export type StudioAgent = z.infer<typeof StudioAgentSchema>;

/** How Pinecall tells an agent to write on each channel: what one that writes its own replaces. */
export async function readChannelRules(credentials: Credentials): Promise<ChannelRules> {
  return ChannelRulesSchema.parse(await read(credentials, "/v1/studio/channel-rules"));
}

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

const SETTINGS_SAVED = "pinecall:settings-saved";

/** Saved, and said to the page: a call open on that agent takes them without hanging up (talk/stages.ts). */
export async function setSettings(credentials: Credentials, agent: string, body: { config: TuningBody; if_version: number | null; note: string | null; team: boolean }): Promise<TuningAnswer> {
  const kept = TuningAnswerSchema.parse(await put(credentials, settingsOf(agent), body));
  window.dispatchEvent(new CustomEvent(SETTINGS_SAVED, { detail: agent }));
  return kept;
}

/** Hear each save of an agent's settings made on this page; returns the unsubscribe function. */
export function onSettingsSaved(heard: (agent: string) => void): () => void {
  const listener = (event: Event): void => heard((event as CustomEvent<string>).detail);
  window.addEventListener(SETTINGS_SAVED, listener);
  return () => window.removeEventListener(SETTINGS_SAVED, listener);
}

/** What the agent's next call runs; with `languages`, what it would run if its callers spoke those, nothing kept. */
export async function readReport(credentials: Credentials, agent: string, languages?: readonly string[]): Promise<Report> {
  const asked = languages === undefined || languages.length === 0 ? undefined : { language: languages.join(", ") };
  return ReportSchema.parse(await read(credentials, `/v1/agents/${encodeURIComponent(agent)}/pipeline`, asked));
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
