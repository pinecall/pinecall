/** Configure's doors: the agent's settings in its corners, what its next call runs on and how its calls measured, voices, and its lexicon. */

import { z } from "zod";

import { answered, doorUrl, headersFor, put, read, type Credentials } from "@pinecall/core/api";
import { type ListedVoice, VoicesListedSchema } from "@pinecall/core/wire/rest-evals";
import { type LexiconAnswer, LexiconAnswerSchema, type LexiconBody, type TuningAnswer, TuningAnswerSchema, type TuningBody } from "@pinecall/core/wire/rest-org";

export type { LexiconAnswer, LexiconBody, ListedVoice, TuningAnswer, TuningBody };

const StageSchema = z.object({ vendor: z.string(), model: z.string().nullable(), voice_id: z.string().nullable(), language: z.string().nullable() });
const ProviderSchema = z.looseObject({ name: z.string(), does: z.array(z.string()), ready: z.boolean(), voices_listed: z.boolean() });

const ReportSchema = z.looseObject({
  hears: StageSchema,
  decides: StageSchema,
  speaks: StageSchema,
  talks: StageSchema.nullish(),
  greeting: z.looseObject({ say: z.string().nullish(), reply: z.string().nullish() }).nullish(),
  providers: z.array(ProviderSchema),
  defaults: z.record(z.string(), z.string()),
  models: z.record(z.string(), z.array(z.string())),
  runs: z.record(z.string(), z.string()),
  voice_defaults: z.record(z.string(), z.string()).default({}),
  calls: z.number(),
  medians: z.array(z.object({ name: z.string(), seconds: z.number(), turns: z.number() })),
});

export type Report = z.infer<typeof ReportSchema>;
export type Provider = Report["providers"][number];
export type Stage = z.infer<typeof StageSchema>;

// The definition goes back whole on a save, so what this page does not draw is kept as it was read.
const StudioAgentSchema = z.looseObject({
  release: z.number().int(),
  definition: z.looseObject({ instructions: z.string(), greeting: z.looseObject({ say: z.string().nullish(), reply: z.string().nullish() }).nullish() }),
});
export type StudioAgent = z.infer<typeof StudioAgentSchema>;

const studioOf = (agent: string): string => `/v1/studio/agents/${encodeURIComponent(agent)}`;

export async function readStudioAgent(credentials: Credentials, agent: string): Promise<StudioAgent> {
  return StudioAgentSchema.parse(await read(credentials, studioOf(agent)));
}

export async function saveStudioAgent(credentials: Credentials, agent: string, definition: StudioAgent["definition"], basedOn: number): Promise<StudioAgent> {
  return StudioAgentSchema.parse(await put(credentials, studioOf(agent), { definition, based_on: basedOn }));
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
