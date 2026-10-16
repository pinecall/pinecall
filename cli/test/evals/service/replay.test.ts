/** Ring 3: one finished call answered by the runtime's code checks, with a policy file's words and budgets. */

import { describe, expect, it } from "vitest";

import { UsageError } from "../../../src/errors.js";
import { readPolicy, replayCall } from "../../../src/evals/service/replay.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { folder, write } from "../../support/project.js";

describe("a replay", () => {
  it("posts the policy for the call and answers the verdicts", async () => {
    const sent = answer("post", "/v1/evals/replay/:call", { call: "call_1", agent: "front-desk", passed: true, verdicts: [] });
    const { ctx } = testContext();
    const policy = readPolicy(write(folder(), "policy.json", JSON.stringify({ banned: ["guarantee"], budget: { e2e_latency: 1.5 } })));
    expect((await replayCall(ctx, "call_1", policy)).passed).toBe(true);
    expect(sent[0]!.path).toBe("/v1/evals/replay/call_1");
    expect(sent[0]!.body).toEqual({ banned: ["guarantee"], budget: { e2e_latency: 1.5 } });
  });

  it("with no policy file sends none, and a file that is not there is the arguments' fault", () => {
    expect(readPolicy(undefined)).toEqual({});
    expect(() => readPolicy("/nowhere.json")).toThrow(UsageError);
  });
});
