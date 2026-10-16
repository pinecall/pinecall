/** The verbs a supervisor sends a call from the desk. */

import { z } from "zod";
import { TransferModeSchema } from "./defs.js";

/** Make the agent say this, verbatim, to the caller. Logged as supervisor.said. */
export const SayVerbSchema = z.strictObject({
  verb: z.literal("say"),
  text: z.string(),
});

/**
 * Tell the agent something the caller never hears. It reaches the agent as an instruction for its
 * next reply; logged as supervisor.whispered.
 */
export const WhisperVerbSchema = z.strictObject({
  verb: z.literal("whisper"),
  text: z.string(),
});

/**
 * The supervisor takes the line: the agent goes quiet and the supervisor's audio replaces it.
 * Logged as supervisor.took_over.
 */
export const TakeoverVerbSchema = z.strictObject({
  verb: z.literal("takeover"),
});

/**
 * The supervisor hands the line back to the agent, which resumes with the history intact. Logged
 * as supervisor.released.
 */
export const ReleaseVerbSchema = z.strictObject({
  verb: z.literal("release"),
});

/**
 * Send the caller to another number. Logged as supervisor.transferred, then call.transferred says
 * whether it worked.
 */
export const TransferVerbSchema = z.strictObject({
  verb: z.literal("transfer"),
  to: z.string(),
  mode: TransferModeSchema.nullish(),
});

/**
 * Hang up on the caller's behalf, at once: a sentence playing and a reply still being written are
 * cut, not finished. Logged as supervisor.ended, then call.ended with reason supervisor_ended.
 */
export const EndVerbSchema = z.strictObject({
  verb: z.literal("end"),
  reason: z.string().nullish(),
});

/** One supervise verb, told apart by its verb field. */
export const VerbSchema = z.discriminatedUnion("verb", [SayVerbSchema, WhisperVerbSchema, TakeoverVerbSchema, ReleaseVerbSchema, TransferVerbSchema, EndVerbSchema]);

export type Verb = z.infer<typeof VerbSchema>;
