/** A suite against the gateway: what a run sends, a busy agent told by its run, the report with latencies and reproductions. */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { PinecallError, UsageError } from "../../../src/errors.js";
import * as suite from "../../../src/evals/service/suite.js";
import { answer, refuse, stream } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { aRun } from "../../support/fixtures.js";
import { folder } from "../../support/project.js";

const GOLDEN = { name: "books-thursday", turns: [{ say: "Thursday at ten?" }], expect: { tools: ["book"] } };

describe("what a run sends", () => {
  it("a written run: the goldens, the models as columns, the app pinned, and nothing about audio", async () => {
    const sent = answer("post", "/v1/evals/run", aRun());
    const { ctx } = testContext();
    await suite.startSuite(ctx, "front-desk", [GOLDEN], suite.SuiteInput.parse({ models: ["haiku", "openai/gpt-5.4-mini"] }), "app_1");
    expect(sent[0]!.body).toEqual({
      agent: "front-desk",
      goldens: [GOLDEN],
      models: [{ provider: "anthropic", model: "claude-haiku-5-5" }, { provider: "openai", model: "gpt-5.4-mini" }],
      app: "app_1",
    });
  });

  it("a spoken run carries its line; cases and a settings version ride beside the goldens", async () => {
    const sent = answer("post", "/v1/evals/run", aRun());
    const { ctx } = testContext();
    await suite.startSuite(ctx, "front-desk", [], suite.SuiteInput.parse({ voice: true, backgroundNoise: 15, ambience: "cafe", packetLoss: 0.05, cases: ["double-booked", "double-booked"], version: 3 }));
    expect(sent[0]!.body).toEqual({ agent: "front-desk", goldens: [], cases: ["double-booked"], version: 3, voice: true, interferer_db: 15, ambience: "cafe", packet_loss: 0.05 });
  });

  it("a run the gateway answered running is followed until its row says it is over", async () => {
    answer("post", "/v1/evals/run", { ...aRun(), status: "running", matrix: null });
    answer("get", "/v1/evals/runs/run_1", aRun());
    const { ctx } = testContext();
    const seen: string[] = [];
    const report = await suite.runSuite(ctx, "front-desk", [GOLDEN], suite.SuiteInput.parse({}), undefined, { onChanged: (run) => seen.push(run.status) });
    expect(seen).toEqual(["running", "done"]);
    expect(report.run.status).toBe("done");
  });

  it("refuses a run of nothing, a model that names none, and packet loss that is no share", async () => {
    const { ctx } = testContext();
    await expect(suite.startSuite(ctx, "front-desk", [], suite.SuiteInput.parse({}))).rejects.toBeInstanceOf(UsageError);
    expect(() => suite.modelsOf(["openai/"])).toThrow(/--model openai\//);
    expect(() => suite.SpokenInput.parse({ packetLoss: 5 })).toThrow(/a share of the packets/);
  });
});

describe("a run", () => {
  it("held when it is done and nothing failed", () => {
    expect(suite.held(aRun())).toBe(true);
    expect(suite.held(aRun([{ metric: "tools", passed: false }]))).toBe(false);
    expect(suite.held({ ...aRun(), status: "running" })).toBe(false);
  });

  it("refused because the agent's run is going is told by that run's id", async () => {
    stream("/v1/events");
    refuse("post", "/v1/evals/run", 409, "a run is going");
    answer("get", "/v1/evals/runs", { runs: [{ ...aRun(), id: "run_7", status: "running" }] });
    answer("get", "/v1/evals/runs/:id", { ...aRun(), id: "run_7", status: "running" });
    const { ctx } = testContext();
    const failed = suite.runSuite(ctx, "front-desk", [GOLDEN], suite.SuiteInput.parse({}), undefined);
    await expect(failed).rejects.toBeInstanceOf(PinecallError);
    await expect(failed).rejects.toThrow("a run is already going on front-desk (run_7) — pinecall runs show run_7 to watch it");
  });

  // A run that held writes no reproduction: one that broke writes into the process's own folder, which writeReproductions covers below.
  it("to its end answers the report: the run, and each call's medians off its log", async () => {
    stream("/v1/events");
    answer("get", "/v1/evals/runs", { runs: [] });
    answer("post", "/v1/evals/run", aRun());
    answer("get", "/v1/calls/:call/events", {
      entries: [
        { seq: 3, type: "turn.agent", data: { metrics: { e2e_latency: 1.2, llm_node_ttft: 0.4 } } },
        { seq: 5, type: "turn.agent", data: { metrics: { e2e_latency: 0.8 } } },
        { seq: 7, type: "turn.agent", data: { metrics: { e2e_latency: 1.0 } } },
      ],
      next: null,
    });
    const { ctx } = testContext();
    const report = await suite.runSuite(ctx, "front-desk", [GOLDEN], suite.SuiteInput.parse({}), undefined);
    expect(report.held).toBe(true);
    expect(report.latencies).toEqual({ call_g1: { e2e_latency: 1.0, llm_node_ttft: 0.4 } });
    expect(report.reproductions).toEqual([]);
  });
});

describe("the report's parts", () => {
  it("medians are of the turns that measured, and a metric never measured is left out", () => {
    const turn = (metrics: Record<string, number>) => ({ seq: 1, type: "turn.agent", data: { metrics } });
    expect(suite.mediansOf([turn({ e2e_latency: 2 }), turn({ e2e_latency: 1 }), { seq: 2, type: "turn.user", data: {} }])).toEqual({ e2e_latency: 1.5 });
  });

  it("a reproduction holds the golden declared, the verdicts, the log, and says why the requests are missing", () => {
    const under = folder();
    const [path] = suite.writeReproductions(aRun([{ metric: "tools", passed: false, reason: "never booked" }]), [GOLDEN], { call_g1: [{ seq: 1, type: "turn.user", data: { text: "Thursday?" } }] }, under);
    const written = JSON.parse(readFileSync(path!, "utf8")) as Record<string, unknown>;
    expect(written).toMatchObject({ run: "run_1", golden: "books-thursday", call: "call_g1", declared: GOLDEN, verdicts: [{ metric: "tools", passed: false, reason: "never booked" }], asked: suite.NOT_RECORDED });
    expect(written["log"]).toHaveLength(1);
  });

  it("nothing broke, nothing written", () => {
    expect(suite.writeReproductions(aRun(), [GOLDEN], {}, folder())).toEqual([]);
  });

  it("a whole log is read page after page while pages come full", async () => {
    const pages = answer("get", "/v1/calls/:call/events", ({ query }) => ({
      entries: query["after"] === "0" ? Array.from({ length: 500 }, (_, at) => ({ seq: at + 1, type: "x", data: {} })) : [{ seq: 501, type: "x", data: {} }],
      next: null,
    }));
    const { ctx } = testContext();
    expect(await suite.allEntries(ctx, "call_1")).toHaveLength(501);
    expect(pages.map((one) => one.query["after"])).toEqual(["0", "500"]);
  });
});
