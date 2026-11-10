/** A vendor's name as a person reads it, and the three stages a call runs through. */

export type Modality = "stt" | "llm" | "tts";

const BRANDS: Readonly<Record<string, string>> = { elevenlabs: "ElevenLabs", openai: "OpenAI", openrouter: "OpenRouter", xai: "xAI", assemblyai: "AssemblyAI", deepgram: "Deepgram", cartesia: "Cartesia", google: "Google", anthropic: "Anthropic", soniox: "Soniox", groq: "Groq" };

export function brandOf(name: string): string {
  return BRANDS[name] ?? `${name.charAt(0).toUpperCase()}${name.slice(1)}`;
}
