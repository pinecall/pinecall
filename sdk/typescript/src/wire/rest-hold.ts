/** The hold melody's door, as the class's process reads and uploads it: what plays, after how long, and the hash of the file that landed. */

import { z } from "zod";

/** GET · PUT /v1/agents/{slug}/pipeline/hold-audio: the runtime's melody, silence, or a clip, with the wait before it. */
export const HoldAudioSchema = z.object({
  played: z.enum(["default", "off", "custom"]),
  sha256: z.string().nullish(),
  /** The hash of the clip as it was uploaded, before conversion: what a class that ships it declares. */
  source_sha256: z.string().nullish(),
  seconds: z.number().nullish(),
  name: z.string().nullish(),
  after_s: z.number(),
  /** True when the agent's class declares its melody: the door takes nothing but the class's own file. */
  fixed: z.boolean().optional(),
});

export type HoldAudio = z.infer<typeof HoldAudioSchema>;
