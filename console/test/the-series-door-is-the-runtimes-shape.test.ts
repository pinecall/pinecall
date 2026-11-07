/** The Observability screen parses the gateway's series day by day and refuses a renamed field. */

import { expect, test } from "vitest";
import { z } from "zod";

import { measured, seriesOf } from "../src/lib/series";

// runtime wire/rest/usage.py: Series, as the door answers it.
const A_DAY = {
  day: "2026-10-09",
  calls: 3,
  finished: 3,
  escalated: 1,
  spend_usd: 0.42,
  mean_length_s: 48.5,
  e2e_median_s: 1.2,
  e2e_p95_s: 2.9,
  endings: [{ reason: "caller_hung_up", count: 3 }],
  stages: [{ stage: "llm", turns: 7, median_s: 0.8, p95_s: 1.6 }],
  judges: [{ name: "grounded", held: 2, judged: 3 }],
  tools_ran: 4,
  tools_failed: 1,
};

test("a day is its calls, endings, cost, latencies, judges and tools, and a renamed field is refused", () => {
  const series = seriesOf({ day: "2026-10-09", days: 7, agent: null, series: [A_DAY] });
  expect(series.series[0]?.stages[0]?.p95_s).toBe(1.6);
  expect(series.series[0]?.judges[0]?.held).toBe(2);
  expect(() => seriesOf({ day: "2026-10-09", days: 7, agent: null, series: [{ ...A_DAY, tools_failed: undefined }] })).toThrow(z.ZodError);
});

test("a window measures something once a turn is timed, a tool ran or a judge spoke, and calls that never reached a turn do not", () => {
  const silent = { ...A_DAY, e2e_median_s: null, e2e_p95_s: null, stages: [], judges: [{ name: "grounded", held: 0, judged: 0 }], tools_ran: 0, tools_failed: 0 };
  expect(measured([silent])).toBe(false);
  expect(measured([])).toBe(false);
  expect(measured([silent, { ...silent, e2e_median_s: 1.1 }])).toBe(true);
  expect(measured([{ ...silent, tools_ran: 1 }])).toBe(true);
  expect(measured([{ ...silent, judges: [{ name: "grounded", held: 0, judged: 1 }] }])).toBe(true);
});
