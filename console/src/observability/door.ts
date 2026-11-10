/** The doors Observability reads: the window's days (GET /v1/insights/series), its tools and slowest turns, the monitors' lines, and the vendors on the org's own key. */

import { useEffect, useRef, useState } from "react";
import { z } from "zod";

import { GatewayError, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { MonitorListSchema, type Monitor } from "@pinecall/core/wire/rest-evals";
import type { WindowDays } from "../lib/insights";

export type { Monitor };

/** What is asked of every door here: how many days, ending today or on `day`, of one agent or of all (""). */
export interface Asked {
  days: WindowDays;
  agent: string;
  day?: string;
}

// runtime wire/rest/usage.py: Series. Loose so a new field does not fail the parse.
const StageSchema = z.object({ stage: z.string(), turns: z.number(), median_s: z.number().nullable(), p95_s: z.number().nullable() });
const JudgeSchema = z.object({ name: z.string(), held: z.number(), judged: z.number() });
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
// `vendors` is a newer runtime's answer: one that does not send it reads as none.
const SeriesSchema = z.looseObject({ day: z.string(), days: z.number(), agent: z.string().nullable(), series: z.array(DaySchema), vendors: z.array(VendorSchema).default([]) });

export type Series = z.infer<typeof SeriesSchema>;
export type SeriesDay = Series["series"][number];
export type SeriesVendor = Series["vendors"][number];

// runtime calls/schemas: ToolsReport.
const ToolSchema = z.object({ name: z.string(), ran: z.number(), failed: z.number(), median_s: z.number().nullable(), last_error: z.object({ call: z.string(), at: z.number(), text: z.string() }).nullable() });
const ToolsSchema = z.looseObject({ tools: z.array(ToolSchema) });

export type ToolStat = z.infer<typeof ToolSchema>;

// runtime calls/schemas: SlowTurns.
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
const SlowSchema = z.looseObject({ turns: z.array(TurnSchema) });

export type SlowTurn = z.infer<typeof TurnSchema>;

const WHAT_MOVES_THE_NUMBERS = ["call.started", "call.ended", "call.summary", "call.score"] as const;
const SLOW_TURNS_SHOWN = 5;

/**
 * One insights door, read on open and when the feed says a call moved it: undefined while asked,
 * null where the box does not have the door or the key may not read it. An answer is only ever
 * the one to what is asked now, never the window or the agent before.
 */
function useInsightDoor<T>(path: string, parse: (answered: unknown) => T, { days, agent, day }: Asked, extra: Readonly<Record<string, number>> = {}): T | null | undefined {
  const credentials = useCredentials();
  const params = { days, ...(day === undefined ? {} : { day }), ...(agent === "" ? {} : { agent }), ...extra };
  const asked = JSON.stringify(params);
  const [held, setHeld] = useState<{ asked: string; answer: T | null } | null>(null);
  // An answer to an earlier question that lands late is dropped, or it would take the place of the one in view.
  const latest = useRef(asked);
  latest.current = asked;

  useFed(
    () => {
      read(credentials, path, params).then(
        (answered) => {
          if (latest.current === asked) setHeld({ asked, answer: parse(answered) });
        },
        (refused: unknown) => {
          if (latest.current === asked && refused instanceof GatewayError && [403, 404].includes(refused.status)) setHeld({ asked, answer: null });
        },
      );
    },
    { types: WHAT_MOVES_THE_NUMBERS },
    [path, asked],
  );

  return held?.asked === asked ? held.answer : undefined;
}

export function useSeries(asked: Asked): Series | null | undefined {
  return useInsightDoor("/v1/insights/series", (answered) => SeriesSchema.parse(answered), asked);
}

/** Every tool of the window, the most failed first. */
export function useTools(asked: Asked): readonly ToolStat[] | null | undefined {
  return useInsightDoor("/v1/insights/tools", (answered) => ToolsSchema.parse(answered).tools, asked);
}

/** The window's slowest turns, the slowest first. */
export function useSlowTurns(asked: Asked): readonly SlowTurn[] | null | undefined {
  return useInsightDoor("/v1/insights/slow", (answered) => SlowSchema.parse(answered).turns, asked, { limit: SLOW_TURNS_SHOWN });
}

/** Whether a window holds anything the page draws: a timed turn, a tool that ran or a judge's verdict. Calls that never reached a turn are not. */
export function measured(days: readonly SeriesDay[]): boolean {
  return days.some((day) => day.e2e_median_s !== null || day.tools_ran > 0 || day.judges.some((judge) => judge.judged > 0));
}

function useReadOnce<T>(path: string, parse: (answered: unknown) => readonly T[]): readonly T[] {
  const credentials = useCredentials();
  const [rows, setRows] = useState<readonly T[]>([]);
  useEffect(() => {
    let gone = false;
    read(credentials, path).then(
      (answered) => !gone && setRows(parse(answered)),
      // A key that may not read it draws the page without it.
      () => undefined,
    );
    return () => {
      gone = true;
    };
    // `parse` is the caller's constant.
  }, [credentials, path]);
  return rows;
}

const monitorsIn = (answered: unknown): readonly Monitor[] => MonitorListSchema.parse(answered).monitors;
const vendorsIn = (answered: unknown): readonly string[] => z.object({ vendors: z.array(z.string()) }).parse(answered).vendors;

/** The lines the org drew (GET /v1/monitors); none for a key that may not read them. */
export function useMonitors(): readonly Monitor[] {
  return useReadOnce("/v1/monitors", monitorsIn);
}

/** The vendors the org runs on its own key (GET /v1/provider-keys); every other is lent by the runtime. */
export function useOwnVendors(): readonly string[] {
  return useReadOnce("/v1/provider-keys", vendorsIn);
}

/** The line the org drew over a number, for every agent or for the one in view. */
export function lineOver(monitors: readonly Monitor[], metric: string | null, agent: string): Monitor | undefined {
  return monitors.find((one) => one.metric === metric && one.above && (one.agent === null || one.agent === agent));
}
