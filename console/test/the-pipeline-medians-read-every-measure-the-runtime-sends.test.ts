/** The pipeline report's medians: the five latencies and the runtime's talk share all read. */
import { expect, test } from "vitest";

import { MeasuredSchema } from "../src/screens/pipeline/door";

test("the agent's talk share parses beside the five latencies, and dead air no more", () => {
  expect(() => MeasuredSchema.parse({ name: "dead_air", seconds: 0.4, turns: 3 })).toThrow();
  for (const name of ["e2e_latency", "talk_share"]) {
    expect(MeasuredSchema.parse({ name, seconds: 0.4, turns: 3 }).name).toBe(name);
  }
  expect(() => MeasuredSchema.parse({ name: "made_up", seconds: 1, turns: 1 })).toThrow();
});
