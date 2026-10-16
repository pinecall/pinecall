/** Insights over whole UTC days (GET /v1/insights), and the window a screen reads them over, kept in its URL. */

import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { z } from "zod";

import { GatewayError, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { Segmented } from "../ui";

const ChannelsSchema = z.object({ phone: z.number(), web: z.number(), whatsapp: z.number() });

// Runtime docs/protocol/console-api.md §2. Days are UTC. Loose so new fields don't fail parsing.
const InsightsSchema = z.looseObject({
  day: z.string(),
  days: z.number(),
  conversations: z.object({ now: z.number(), before: z.number() }),
  resolved_rate: z.number().nullable(),
  median_e2e_s: z.number().nullable(),
  spend_usd: z.number(),
  channels: ChannelsSchema,
  judged: z.number(),
  passed: z.number(),
  escalated: z.number(),
  mean_length_s: z.number().nullable(),
  endings: z.array(z.object({ reason: z.string(), count: z.number() })),
  series: z.array(ChannelsSchema.extend({ day: z.string(), spend_usd: z.number(), judged: z.number(), passed: z.number() })),
  sessions_total: z.number(),
  live: z.number(),
  agents: z.array(
    z.object({
      slug: z.string(),
      calls: z.number(),
      score: z.number().nullable(),
      spend: z.object({ llm_usd: z.number(), stt_usd: z.number(), tts_usd: z.number(), phone_usd: z.number(), platform_usd: z.number(), minutes: z.number(), per_minute_usd: z.number().nullable() }),
    }),
  ),
  budget: z.object({ limit_usd: z.number().nullable(), spent_usd_month: z.number() }),
});
export type Insights = z.infer<typeof InsightsSchema>;

/** One UTC day of a window, as the door counts it. */
export type InsightsDay = Insights["series"][number];

/** The windows a screen offers, in whole UTC days: the door answers these and no other. */
export const WINDOWS = [
  { days: 1, label: "24 h", said: "today" },
  { days: 7, label: "7 d", said: "the last 7 days" },
  { days: 30, label: "30 d", said: "the last 30 days" },
] as const;

export type WindowDays = (typeof WINDOWS)[number]["days"];

/** What is asked: the window's last day (today when absent), how many days, one agent or all. */
export interface Asked {
  day?: string | undefined;
  days?: WindowDays | undefined;
  agent?: string | undefined;
}

// What changes the numbers: a call starting or ending is the live count and the minutes, its summary
// the spend and the endings, its score the judged and the passed.
export const WHAT_MOVES_THE_NUMBERS = ["call.started", "call.ended", "call.summary", "call.score"] as const;

/** Read insights on open and when the feed says a call moved them; null until loaded, or when the gateway refuses with 403/404. */
export function useInsights({ day, days = 1, agent }: Asked = {}): Insights | null {
  const credentials = useCredentials();
  const [insights, setInsights] = useState<Insights | null>(null);

  useFed(
    () => {
      const params = { days, ...(day === undefined ? {} : { day }), ...(agent === undefined ? {} : { agent }) };
      read(credentials, "/v1/insights", params).then(
        (answered) => setInsights(InsightsSchema.parse(answered)),
        (refused: unknown) => {
          // Missing door or no permission: nothing to show.
          if (refused instanceof GatewayError && [403, 404].includes(refused.status)) setInsights(null);
        },
      );
    },
    { types: WHAT_MOVES_THE_NUMBERS },
    [day, days, agent],
  );

  return insights;
}

/** The window this screen is read over (`?days=` in its URL, `fallback` when absent), a way to pick another, and whether one was picked. */
export function useWindowDays(fallback: WindowDays = 1): [WindowDays, (days: WindowDays) => void, boolean] {
  const [search, setSearch] = useSearchParams();
  const asked = Number(search.get("days"));
  const picked = WINDOWS.find((option) => option.days === asked)?.days;
  const pick = (chosen: WindowDays): void => {
    const next = new URLSearchParams(search);
    if (chosen === fallback) next.delete("days");
    else next.set("days", String(chosen));
    setSearch(next, { replace: true });
  };
  return [picked ?? fallback, pick, picked !== undefined];
}

/** How a window is said in a sentence: "today", "the last 7 days". */
export function windowSaid(days: WindowDays): string {
  return WINDOWS.find((option) => option.days === days)?.said ?? "today";
}

/** The three windows as one control. */
export function WindowPicker({ days, onPick }: { days: WindowDays; onPick: (days: WindowDays) => void }): ReactNode {
  return (
    <Segmented
      options={WINDOWS.map((option) => ({ value: String(option.days), label: option.label }))}
      value={String(days)}
      onChange={(chosen) => onPick(WINDOWS.find((option) => String(option.days) === chosen)?.days ?? 1)}
    />
  );
}
