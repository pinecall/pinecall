/** A stage as a class names it in short: `"vendor/model"` for a model, `"vendor/voice"` for a voice, alone or with its options. */

import { DeclarationRefused } from "./tools.js";

/** A model by its vendor and its id, which keeps every slash after the vendor's: `livekit/openai/gpt-5-mini`. */
export function modelOf(named: string): { provider: string; model: string } {
  const slash = named.indexOf("/");
  if (slash < 0) return { provider: named, model: "" };
  return { provider: named.slice(0, slash), model: named.slice(slash + 1) };
}

/**
 * A model stage as the declaration carries it, from what a class wrote: `"vendor/model"`, the same
 * under `model` with the stage's options beside it (`{ model: "openai/gpt-5.4-mini", temperature: 0.3 }`),
 * or the declaration's own shape, left as it is.
 */
export function stageOf(field: string, given: unknown): unknown {
  if (typeof given === "string" && given.trim() !== "") return modelOf(given.trim());
  if (typeof given !== "object" || given === null) throw new DeclarationRefused(`static ${field} is "vendor/model", or { model: "vendor/model", … } with its options`);
  const { model, ...rest } = given as { model?: unknown; provider?: unknown };
  if (rest.provider !== undefined || typeof model !== "string") return given;
  return { ...rest, ...modelOf(model) };
}

/**
 * A voice as the declaration carries it: `"vendor/voice"`, the same under `voice` with its options
 * (`{ voice: "cartesia/<id>", model: "sonic-2" }`), or the declaration's own shape, left as it is.
 */
export function voiceOf(given: unknown): unknown {
  if (typeof given === "string") return named(given);
  if (typeof given !== "object" || given === null) throw new DeclarationRefused(NOT_A_VOICE);
  const { voice, ...rest } = given as { voice?: unknown; provider?: unknown };
  if (rest.provider !== undefined || voice === undefined) return given;
  if (typeof voice !== "string") throw new DeclarationRefused(NOT_A_VOICE);
  return { ...rest, ...named(voice) };
}

const NOT_A_VOICE = 'voice is "vendor/voice", the vendor and its own id for the voice, or { voice: "vendor/voice", … } with its options';

function named(voice: string): { provider: string; voiceId: string } {
  const slash = voice.indexOf("/");
  if (slash <= 0 || slash === voice.length - 1) throw new DeclarationRefused(NOT_A_VOICE);
  return { provider: voice.slice(0, slash), voiceId: voice.slice(slash + 1) };
}
