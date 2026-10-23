/** `pinecall test | eval | runs | cases | personas` as typed: a suite run and its exit, a replay, the runs, the inbox, the callers. */

import { describe, expect, it } from "vitest";

import { answer, refuse, stream } from "../support/gateway.js";
import { A_CASE, A_PERSONA, aRun } from "../support/fixtures.js";
import { folder, project, write } from "../support/project.js";
import { run, runJson } from "../support/run.js";

const GOLDENS = { "agents/front-desk/test/goldens/books-thursday.json": JSON.stringify({ turns: [{ say: "Thursday at ten?" }], expect: { tools: ["book"] } }) };

describe("pinecall test", () => {
  it("runs the agent's goldens and exits 0 when every one held", async () => {
    stream("/v1/events");
    answer("get", "/v1/evals/runs", { runs: [] });
    const sent = answer("post", "/v1/evals/run", aRun());
    answer("get", "/v1/calls/:call/events", { entries: [], next: null });
    const ran = await run(["test"], { cwd: project(["front-desk"], GOLDENS) });
    expect(ran.code).toBe(0);
    expect((sent[0]!.body as { goldens: { name: string }[] }).goldens.map((one) => one.name)).toEqual(["books-thursday"]);
  });

  it("with nothing said plays the files and the approved dataset, and marks each golden file or case", async () => {
    stream("/v1/events");
    answer("get", "/v1/evals/runs", { runs: [] });
    const played = aRun();
    const fromTheDataset = { ...played.matrix.runs[0]!, golden: "double-booked" };
    const sent = answer("post", "/v1/evals/run", {
      ...played,
      calls: [...played.calls, { golden: "double-booked", model: "declared", call: "call_g2" }],
      matrix: { ...played.matrix, goldens: ["books-thursday", "double-booked"], runs: [played.matrix.runs[0]!, fromTheDataset] },
    });
    answer("get", "/v1/calls/:call/events", { entries: [], next: null });
    const ran = await run(["test"], { cwd: project(["front-desk"], GOLDENS) });
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toMatchObject({ dataset: true, goldens: [{ name: "books-thursday" }] });
    expect(ran.out).toContain("front-desk · 1 golden · the dataset · the app's own model · run_1\n");
    expect(ran.out).toContain("  ✓ books-thursday  file\n  ✓ double-booked  case\n");
  });

  it("--files plays the files alone, as before", async () => {
    stream("/v1/events");
    answer("get", "/v1/evals/runs", { runs: [] });
    const sent = answer("post", "/v1/evals/run", aRun());
    answer("get", "/v1/calls/:call/events", { entries: [], next: null });
    await run(["test", "--files"], { cwd: project(["front-desk"], GOLDENS) });
    expect(sent[0]!.body).not.toHaveProperty("dataset");
  });

  it("--json is the report whole", async () => {
    stream("/v1/events");
    answer("get", "/v1/evals/runs", { runs: [] });
    answer("post", "/v1/evals/run", aRun());
    answer("get", "/v1/calls/:call/events", { entries: [], next: null });
    const report = await runJson<{ held: boolean; run: { id: string } }>(["test"], { cwd: project(["front-desk"], GOLDENS) });
    expect([report.held, report.run.id]).toEqual([true, "run_1"]);
  });

  it("refuses an agent with no goldens, and a grep that matched none, before anything is run", async () => {
    expect((await run(["test"])).err).toContain("no goldens at");
    const ran = await run(["test", "--grep", "refund"], { cwd: project(["front-desk"], GOLDENS) });
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("no golden matched --grep refund");
  });

  it("--watch with cases alone is refused: there is no file to watch", async () => {
    expect((await run(["test", "--dataset", "--watch"])).code).toBe(2);
  });

  it("refuses noise on a written run, and packet loss that is no share", async () => {
    expect((await run(["test", "--packet-loss", "5"], { cwd: project(["front-desk"], GOLDENS) })).code).toBe(2);
  });
});

describe("pinecall eval", () => {
  it("prints each check and exits 1 when one broke", async () => {
    answer("post", "/v1/evals/replay/:call", {
      call: "call_1",
      agent: "front-desk",
      passed: false,
      verdicts: [
        { check: "banned", status: "broken", detail: "said guarantee at seq 14" },
        { check: "e2e_latency", status: "held", detail: "1.1s under 1.5s" },
      ],
    });
    const ran = await run(["eval", "call_1"]);
    expect(ran.code).toBe(1);
    expect(ran.out).toBe("call_1  front-desk\n  banned       broken    said guarantee at seq 14\n  e2e_latency  held      1.1s under 1.5s\n");
  });
});

describe("pinecall runs", () => {
  it("alone lists the runs: id, when, agent, status, how many cells held", async () => {
    const sent = answer("get", "/v1/evals/runs", { runs: [aRun([{ metric: "tools", passed: false }])] });
    const ran = await run(["runs", "--limit", "5"]);
    expect(sent[0]!.query).toEqual({ limit: "5" });
    expect(ran.out).toMatch(/^run_1 {2}\d{4}-\d{2}-\d{2} \d{2}:\d{2} {2}front-desk {8}done {5}0\/1\n$/);
  });

  it("diff names what moved", async () => {
    answer("get", "/v1/evals/runs/:id", ({ path }) => (path.endsWith("run_1") ? aRun([{ metric: "tools", passed: true }], "run_1") : aRun([{ metric: "tools", passed: false, reason: "never booked" }], "run_2")));
    expect((await run(["runs", "diff", "run_1", "run_2"])).out).toBe("run_1 → run_2\n  books-thursday  tools  held → broken  never booked\n");
  });

  it("drift takes the project's agent, needs one outside a project, and a window it can read", async () => {
    expect((await run(["runs", "drift"], { cwd: folder() })).code).toBe(2);
    expect((await run(["runs", "drift", "--window", "a week"])).err).toContain("a window is a number and one of s, m, h, d");
  });
});

describe("pinecall cases", () => {
  it("alone is the inbox: how many wait, then a row per case", async () => {
    answer("get", "/v1/evals/cases", { cases: [A_CASE], pending: 1, pending_at_most: 50 });
    const ran = await run(["cases"]);
    expect(ran.out).toMatch(/^1 waiting of at most 50\npending\s+double-booked\s+/);
  });

  it("--agent reads a slug from any folder", async () => {
    const sent = answer("get", "/v1/evals/cases", { cases: [], pending: 0, pending_at_most: 50 });
    const ran = await run(["cases", "--agent", "sales"], { cwd: folder() });
    expect(ran.code).toBe(0);
    expect(sent[0]!.query).toEqual({ agent: "sales" });
  });

  it("dismiss --note without the judge that was wrong is refused", async () => {
    answer("get", "/v1/evals/cases", { cases: [A_CASE] });
    expect((await run(["cases", "dismiss", "double-booked", "--note", "why"])).code).toBe(2);
  });

  it("add keeps a golden file as an approved case and prints it; a name a call made is the gateway's sentence, exit 1", async () => {
    const dir = folder();
    const file = write(dir, "no-price.json", JSON.stringify({ turns: [{ say: "How much is a crown?" }], expect: { not: ["euros"] } }));
    answer("put", "/v1/agents/:slug/cases/:name", { ...A_CASE, name: "no-price", status: "approved", source: "person", source_call: null, held_out: true });
    const ran = await run(["cases", "add", file, "--held-out"]);
    expect(ran.code).toBe(0);
    expect(ran.out).toBe("no-price · front-desk · person · approved · held out\n");
    refuse("put", "/v1/agents/:slug/cases/:name", 409, "no-price was made by call_9: a case a call made is not rewritten");
    const refused = await run(["cases", "add", file]);
    expect(refused.code).toBe(1);
    expect(refused.err).toContain("a case a call made is not rewritten");
  });

  it("add refuses a folder with exit 2", async () => {
    const ran = await run(["cases", "add", folder()]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("never a folder");
  });

  it("keep needs a name", async () => {
    expect((await run(["cases", "keep", "call_9"])).code).toBe(2);
  });
});

describe("pinecall personas", () => {
  it("alone lists the agent's callers", async () => {
    answer("get", "/v1/agents/:slug/personas", { personas: [{ ...A_PERSONA, name: "confused-elder", owner: "pinecall", on: false, summary: "an elder who mishears" }, A_PERSONA] });
    const ran = await run(["personas"]);
    expect(ran.out).toMatch(/confused-elder\s+pinecall off\s+an elder who mishears\n/);
    expect(ran.out).toMatch(/apurado\s+yours\s+book the first slot tomorrow\n/);
  });

  it("add takes the facts as what=said", async () => {
    answer("get", "/v1/agents/:slug/personas", { personas: [] });
    const sent = answer("put", "/v1/agents/:slug/personas/:name", { personas: [A_PERSONA] });
    const ran = await run(["personas", "add", "apurado", "--goal", "book tomorrow", "--style", "curt", "--fact", "name=Luis", "--fact", "phone=305 555 0101"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toMatchObject({ goal: "book tomorrow", style: "curt", facts: { name: "Luis", phone: "305 555 0101" } });
  });

  it("generate refuses more than ten", async () => {
    expect((await run(["personas", "generate", "11"])).code).toBe(2);
  });
});
