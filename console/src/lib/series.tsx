/** Series over whole UTC days (GET /v1/insights/series): what the Observability screen draws, read like the insights. */

import { useState } from "react";
import { z } from "zod";

import { GatewayError, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { type Asked, WHAT_MOVES_THE_NUMBERS } from "./insights";

// runtime wire/rest/usage.py: Series. Loose so a new field does not fail the parse.
const StageSchema = z.object({ stage: z.string(), turns: z.number(), median_s: z.number().nullable(), p95_s: z.number().nullable() });
const JudgeSchema = z.object({ name: z.string(), held: z.number(), judged: z.number() });
// The window's turns per stage, vendor and model: what answered, and how fast.
const VendorSchema = z.object({ stage: z.string(), vendor: z.string(), model: z.string().nullable(), turns: z.number(), median_s: z.number().nullable(), p95_s: z.number().nullable() });
const DaySchema = z.looseObject({
  day: z.string(),
  calls: z.number(),
  finished: z.number(),
  escalated: z.number(),
  spend_usd: z.number(),
  mean_length_s: z.number().nullable(),
  e2e_median_s: z.number().nullable(),
  e2e_p95_s: z.number().nullable(),
  endings: z.array(z.object({ reason: z.string(), count: z.number() })),
  stages: z.array(StageSchema),
  judges: z.array(JudgeSchema),
  tools_ran: z.number(),
  tools_failed: z.number(),
});
// `vendors` is a box's newer answer: a runtime that does not send it reads as none.
const SeriesSchema = z.looseObject({ day: z.string(), days: z.number(), agent: z.string().nullable(), series: z.array(DaySchema), vendors: z.array(VendorSchema).default([]) });

export type Series = z.infer<typeof SeriesSchema>;
/** One UTC day of the window, every number a chart draws. */
export type SeriesDay = Series["series"][number];
/** One vendor and model over the whole window, for one stage. */
export type SeriesVendor = Series["vendors"][number];

/** Parse what the door answered; a renamed field is refused. */
export function seriesOf(answered: unknown): Series {
  return SeriesSchema.parse(answered);
}

/** Read the series on open and when the feed says a call moved it; null until loaded, or when the gateway refuses with 403/404. */
export function useSeries({ day, days = 7, agent }: Asked = {}): Series | null {
  const credentials = useCredentials();
  const [series, setSeries] = useState<Series | null>(null);

  useFed(
    () => {
      const params = { days, ...(day === undefined ? {} : { day }), ...(agent === undefined ? {} : { agent }) };
      read(credentials, "/v1/insights/series", params).then(
        (answered) => setSeries(seriesOf(answered)),
        (refused: unknown) => {
          if (refused instanceof GatewayError && [403, 404].includes(refused.status)) setSeries(null);
        },
      );
    },
    { types: WHAT_MOVES_THE_NUMBERS },
    [day, days, agent],
  );

  return series;
}
