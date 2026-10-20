/** Start a simulated call: the gateway plays the persona against whatever holds the agent — deployed, or a `pinecall start` — written or spoken. */

import { z } from "zod";

import { post, type Credentials } from "@pinecall/core/api";

// runtime wire/rest/evals.py SimulationStarted.
const StartedSchema = z.strictObject({ call: z.string(), voice: z.boolean() });

/** What a simulation is started with (runtime wire/rest/evals.py SimulationRequest). */
export interface Wanted {
  agent: string;
  persona: string;
  voice: boolean;
  turns: number;
  /** Spoken alone: dB of a voice under the caller's. */
  interferer_db?: number;
  /** Spoken alone: the share of the caller's packets lost, 0 to 1. */
  packet_loss?: number;
  /** Spoken alone: what plays behind the caller at that level; the persona's own when left out. */
  ambience?: "television" | "cafe" | "office" | "street";
  /** Who plays the caller this run, over the persona's own; each unsaid stays the persona's. */
  played_by?: { llm?: string; tts?: string; voice?: string };
}

/** What a run names of who plays its callers: only the words chosen, or nothing at all. */
export function playedBy(played: { llm: string; tts: string; voice: string }): Pick<Wanted, "played_by"> {
  const chosen = Object.fromEntries(Object.entries(played).filter(([, word]) => word !== ""));
  return Object.keys(chosen).length === 0 ? {} : { played_by: chosen };
}

/**
 * POST /v1/simulations answers the call's id at once and plays the conversation in the gateway, so
 * the screen opens the call and watches it as any call is watched. What can be refused — a persona
 * nobody wrote, nobody holding the agent, the org's limits — is refused here, in the gateway's words.
 */
export async function startSimulation(credentials: Credentials, wanted: Wanted): Promise<string> {
  return StartedSchema.parse(await post(credentials, "/v1/simulations", wanted)).call;
}
