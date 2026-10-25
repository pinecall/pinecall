/** What an agent publishes for pages: lines recorded once in its voice, read by any page with no key. */

import { z } from "zod";

/** A written word of a recorded line, and when it is said, in ms from the start of its audio. */
export const RecordedWordSchema = z.strictObject({
  text: z.string(),
  start_ms: z.int(),
  end_ms: z.int(),
});

/** A line recorded in the agent's voice: its MP3's URL, its length, and when each written word is said. */
export const RecordedLineSchema = z.strictObject({
  id: z.string(),
  text: z.string(),
  url: z.string(),
  duration_ms: z.int(),
  voice: z.string(),
  /** False where the voice times no words, and each word was placed by its length. */
  timed: z.boolean(),
  words: z.array(RecordedWordSchema),
});

export type RecordedLine = z.infer<typeof RecordedLineSchema>;

/** POST /v1/agents/{slug}/lines, the answer: the lines asked for, in their order, each recorded once. */
export const RecordedLinesSchema = z.strictObject({
  lines: z.array(RecordedLineSchema),
});
