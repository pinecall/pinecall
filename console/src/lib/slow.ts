/** The slowest turns of a window (GET /v1/insights/slow): which call, which turn, how long, and where the time went. */

import { z } from "zod";

import { type Asked } from "./insights";
import { useInsightDoor } from "./insight-door";

// runtime calls/schemas.py: SlowTurns.
const TurnSchema = z.object({
  call: z.string(),
  agent: z.string(),
  seq: z.number(),
  name: z.string().nullable(),
  at: z.number(),
  e2e_s: z.number(),
  hears_s: z.number().nullable(),
  thinks_s: z.number().nullable(),
  tools_s: z.number().nullable(),
  speaks_s: z.number().nullable(),
});
const SlowSchema = z.looseObject({ day: z.string(), days: z.number(), agent: z.string().nullable(), turns: z.array(TurnSchema) });

export type SlowTurns = z.infer<typeof SlowSchema>;
export type SlowTurn = SlowTurns["turns"][number];

const HOW_MANY = 3;

export function useSlowTurns(asked: Asked): SlowTurns | null | undefined {
  return useInsightDoor("/v1/insights/slow", (answered) => SlowSchema.parse(answered), asked, { limit: HOW_MANY });
}
