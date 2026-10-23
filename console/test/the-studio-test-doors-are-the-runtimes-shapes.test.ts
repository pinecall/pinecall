/** Studio's Test runs the agent's cases through the evals doors: the post names the agent and the cases alone, the read is the run by its id, and a renamed field is refused. */

import { expect, test } from "vitest";
import { z } from "zod";

import { readRun, runCases } from "../src/screens/evals/door";

const CREDENTIALS = { base: "/", key: "pk_test" };

// runtime wire/rest/evals.py: EvalRun as POST /v1/evals/run answers it, the matrix null until judged.
const A_RUN = {
  id: "run_7c2e9b1d3a4f",
  agent: "front-desk",
  started_at: 1791460000.5,
  finished_at: null,
  status: "running",
  calls: [],
  matrix: null,
  error: null,
};

const JUDGED = {
  ...A_RUN,
  finished_at: 1791460090.5,
  status: "done",
  calls: [{ golden: "no-dice-un-precio", model: "openai/gpt-5.4-mini", call: "call_29d7c7" }],
  matrix: {
    models: ["openai/gpt-5.4-mini"],
    goldens: ["no-dice-un-precio"],
    metrics: ["silence", "grounded"],
    judge_calls: 2,
    runs: [
      {
        model: "openai/gpt-5.4-mini",
        golden: "no-dice-un-precio",
        scores: [
          { metric: "silence", score: 0, passed: false, reason: "it said “80 euros”", criteria: "never says €, euros", judge_calls: 1 },
          { metric: "grounded", score: 1, passed: true, reason: "", criteria: "states nothing the call did not carry", judge_calls: 1 },
        ],
        summary: null,
      },
    ],
    failures: [],
  },
};

let asked: { method: string; url: string; body: unknown }[] = [];

function answering(body: unknown): void {
  asked = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (url: URL, init?: RequestInit) => {
    asked.push({ method: init?.method ?? "GET", url: String(url), body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) });
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
}

test("a run of a Studio agent's cases is a POST naming the agent and the cases, no goldens and no version", async () => {
  answering(A_RUN);
  const run = await runCases(CREDENTIALS, "front-desk", ["no-dice-un-precio", "abre-en-book"], undefined);
  expect(run.status).toBe("running");
  expect(run.matrix).toBeNull();
  expect(asked[0]).toEqual({ method: "POST", url: "https://cloud.pinecall.io/v1/evals/run", body: { agent: "front-desk", cases: ["no-dice-un-precio", "abre-en-book"] } });
});

test("the run is read back by its id until it is over, its matrix the runtime's cells field for field", async () => {
  answering(JUDGED);
  const run = await readRun(CREDENTIALS, A_RUN.id);
  expect(asked[0]).toMatchObject({ method: "GET", url: `https://cloud.pinecall.io/v1/evals/runs/${A_RUN.id}` });
  expect(run.status).toBe("done");
  expect(run.matrix?.runs[0]?.scores[0]).toMatchObject({ metric: "silence", passed: false, reason: "it said “80 euros”" });
  answering({ ...JUDGED, status: "finished" });
  await expect(readRun(CREDENTIALS, A_RUN.id)).rejects.toBeInstanceOf(z.ZodError);
  answering({ ...JUDGED, matrix: { ...JUDGED.matrix, runs: [{ ...JUDGED.matrix.runs[0], scores: [{ metric: "silence", passed: false }] }] } });
  await expect(readRun(CREDENTIALS, A_RUN.id)).rejects.toBeInstanceOf(z.ZodError);
});
