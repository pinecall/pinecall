/** The Observability screen parses the gateway's series day by day and refuses a renamed field. */

import { expect, test } from "vitest";
import { z } from "zod";

import { seriesOf } from "../src/lib/series";

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
