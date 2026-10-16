/** Voice picker API: list a vendor's voices and fetch a sample. */

import { type ListedVoice, type VoiceSample, VoicesListedSchema } from "@pinecall/core/wire/rest-evals";

import { answered, doorUrl, headersFor, read, type Credentials } from "@pinecall/core/api";

export type { ListedVoice, VoiceSample };

/** Vendor's voices in the agent's language, or all languages when none is declared. */
export async function readVoices(credentials: Credentials, tts: string, language: string | null): Promise<ListedVoice[]> {
  const params: Record<string, string> = language === null ? { tts } : { tts, language };
  return VoicesListedSchema.parse(await read(credentials, "/v1/voices", params)).voices;
}

/** Sample as a blob URL plus vendor time to first audio. The caller revokes the URL. */
export interface Heard {
  url: string;
  firstAudioMs: number | null;
}

// <audio src> can't send the auth header, so the WAV is fetched with the key and played as a blob.
// Vendor time to first audio comes in Server-Timing.
/** Synthesize a sentence with one voice, as a call would. */
export async function heard(credentials: Credentials, asked: VoiceSample): Promise<Heard> {
  const answer = await fetch(doorUrl(credentials, "/v1/voices/sample"), {
    method: "POST",
    headers: { ...headersFor(credentials), "content-type": "application/json" },
    body: JSON.stringify(asked),
  });
  if (!answer.ok) await answered(answer);
  return { url: URL.createObjectURL(await answer.blob()), firstAudioMs: firstAudioIn(answer.headers.get("server-timing") ?? "") };
}

/** Parse `first-audio;dur=…` from Server-Timing; null when absent. */
export function firstAudioIn(header: string): number | null {
  const found = /(?:^|,)\s*first-audio;dur=([0-9.]+)/.exec(header);
  return found === null ? null : Math.round(Number(found[1]));
}
