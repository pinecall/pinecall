/** The gateway's count of a window of whole UTC days (GET /v1/insights), read again when a call moves it. */

import { useRef, useState } from "react";
import { z } from "zod";

import { read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";

const InsightsSchema = z.looseObject({
  day: z.string(),
  days: z.number(),
  conversations: z.object({ now: z.number(), before: z.number() }),
  resolved_rate: z.number().nullable(),
  median_e2e_s: z.number().nullable(),
  spend_usd: z.number(),
  judged: z.number(),
  passed: z.number(),
  escalated: z.number(),
  mean_length_s: z.number().nullable(),
  channels: z.object({ phone: z.number(), web: z.number(), whatsapp: z.number() }),
  budget: z.object({ limit_usd: z.number().nullable(), spent_usd_month: z.number() }),
  endings: z.array(z.object({ reason: z.string(), count: z.number() })),
  series: z.array(z.object({ day: z.string(), phone: z.number(), web: z.number(), whatsapp: z.number(), spend_usd: z.number(), judged: z.number(), passed: z.number() })),
  agents: z.array(z.object({ slug: z.string(), calls: z.number(), score: z.number().nullable(), spend: z.object({ minutes: z.number(), llm_usd: z.number(), stt_usd: z.number(), tts_usd: z.number(), phone_usd: z.number(), platform_usd: z.number(), per_minute_usd: z.number().nullable() }).loose() })),
});

export type Insights = z.infer<typeof InsightsSchema>;
export type InsightsDay = Insights["series"][number];

export type WindowDays = 1 | 7 | 30;

const WHAT_MOVES_THE_NUMBERS = ["call.started", "call.ended", "call.summary", "call.score"] as const;

/** The window that ends today, or on `day`, of every agent or one, in this world or the one named; null until it is read. */
export function useInsights(days: WindowDays, { day, agent, world }: { day?: string; agent?: string; world?: "production" | "sandbox" } = {}): Insights | null {
  const held = useCredentials();
  const credentials = world === undefined ? held : { ...held, world };
  const [insights, setInsights] = useState<Insights | null>(null);
  const latest = useRef("");
  const answeredFor = useRef("");
  useFed(
    () => {
      const params = { days, ...(day === undefined ? {} : { day }), ...(agent === undefined ? {} : { agent }) };
      const asked = JSON.stringify(params);
      latest.current = asked;
      read(credentials, "/v1/insights", params).then(
        (answered) => {
          if (latest.current !== asked) return;
          answeredFor.current = asked;
          setInsights(InsightsSchema.parse(answered));
        },
        () => {
          // A read that fails after one that answered changes nothing: the numbers on the page are still the last ones known.
          if (latest.current === asked && answeredFor.current !== asked) setInsights(null);
        },
      );
    },
    { types: WHAT_MOVES_THE_NUMBERS },
    [days, day, agent, world],
  );
  return insights;
}

export function callsOf(day: InsightsDay): number {
  return day.phone + day.web + day.whatsapp;
}
