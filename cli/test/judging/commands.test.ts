/** `pinecall judges | judging` as typed: the table, a try a line per call, `judging on|off` one word, a 409 in the gateway's words. */

import { describe, expect, it } from "vitest";

import { answer, refuse } from "../support/gateway.js";
import { A_JUDGE, A_LIBRARY_JUDGE, JUDGING, SETTINGS, tuningRow } from "../support/fixtures.js";
import { folder } from "../support/project.js";
import { run } from "../support/run.js";

describe("pinecall judges", () => {
  it("alone lists the agent's: whose, the switch, a recommended one marked", async () => {
    const sent = answer("get", "/v1/agents/:slug/judges", { judges: [A_LIBRARY_JUDGE, A_JUDGE] });
    const ran = await run(["judges"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/judges");
    expect(ran.out).toMatch(/consent\s+pinecall\s+off · recommended\s+verdict\s+always/);
    expect(ran.out).toMatch(/offers-next-slot\s+front-desk\s+on\s+verdict/);
  });

  it("show prints one judge whole; a name the list has not is exit 2", async () => {
    answer("get", "/v1/agents/:slug/judges", { judges: [A_LIBRARY_JUDGE, A_JUDGE] });
    const shown = await run(["judges", "show", "consent"]);
    expect(shown.code).toBe(0);
    expect(shown.out).toMatch(/^consent · pinecall · off · recommended\n/);
    expect(shown.out).toContain("asks     The caller consented to being recorded.");
    const missing = await run(["judges", "show", "nope"]);
    expect(missing.code).toBe(2);
    expect(missing.err).toContain("front-desk has no judge called nope");
  });

  it("agreement prints each judge against its labels, and says how far an unjudged one is from being judged", async () => {
    const sent = answer("get", "/v1/evals/calibration", {
      judges: [
        { judge: "offers-next-slot", labelled: 12, compared: 11, agreed: 8, rate: 0.727, trusted: false },
        { judge: "consent", labelled: 3, compared: 2, agreed: 2, rate: 1, trusted: null },
      ],
      labels_to_judge: 10,
      agrees_at_least: 0.8,
    });
    const ran = await run(["judges", "agreement"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.query).toEqual({ agent: "front-desk" });
    expect(ran.out).toMatch(/offers-next-slot\s+12\s+11\s+8\s+73%\s+no/);
    expect(ran.out).toMatch(/consent\s+3\s+2\s+2\s+100%\s+\? · 8 more to compare/);
    expect(ran.out).toContain("trusted from 10 compared labels, agreeing with 80% of them at least");
  });

  it("agreement --org reads every agent's, and says how to label when nobody has", async () => {
    const sent = answer("get", "/v1/evals/calibration", { judges: [], labels_to_judge: 10, agrees_at_least: 0.8 });
    const ran = await run(["judges", "agreement", "--org"], { cwd: folder() });
    expect(sent[0]!.query).toEqual({});
    expect(ran.out).toContain("no judge of the org has been labelled yet: `pinecall cases dismiss <case> --judge-was-wrong <judge>`");
  });

  it("--org lists the org's, from any folder", async () => {
    answer("get", "/v1/org/judges", { judges: [] });
    const ran = await run(["judges", "--org"], { cwd: folder() });
    expect(ran.out).toContain("the org has no judges yet");
  });

  it("add writes it and says how many the list holds", async () => {
    const sent = answer("put", "/v1/agents/:slug/judges/:name", { judges: [A_JUDGE] });
    const ran = await run(["judges", "add", "offers-next-slot", "--asks", A_JUDGE.question, "--answer", "score"]);
    expect(sent[0]!.body).toEqual({ question: A_JUDGE.question, answer: "score", when: "always" });
    expect(ran.out).toBe("offers-next-slot written · 1 judge(s) in the list\n");
  });

  it("rm of one of Pinecall's: the gateway's 409 in its words, which name the verb that switches it off", async () => {
    refuse("delete", "/v1/agents/:slug/judges/:name", 409, "consent is one of Pinecall's judges and is never deleted: `pinecall judges off consent` turns it off");
    const ran = await run(["judges", "rm", "consent"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toBe("pinecall: the gateway answered 409: consent is one of Pinecall's judges and is never deleted: `pinecall judges off consent` turns it off\n");
  });

  it("try prints a line per call and what it cost, writing nothing", async () => {
    const sent = answer("post", "/v1/agents/:slug/judges/try", {
      rows: [
        { call: "CA_8f4a2c", judgment: { name: "offers-next-slot", verdict: "held", criteria: "", reason: "Offered Thursday at 09:30 unasked.", evidence: { seqs: [14] } } },
        { call: "CA_1b", judgment: null, not_judged: "the call is still live" },
      ],
      evals: 1,
      cost_usd: 0.0031,
    });
    const ran = await run(["judges", "try", "offers-next-slot", "--calls", "CA_8f4a2c, CA_1b"]);
    expect(sent[0]!.body).toEqual({ name: "offers-next-slot", calls: ["CA_8f4a2c", "CA_1b"] });
    expect(ran.out).toContain("CA_8f4a2c  ✓ held  Offered Thursday at 09:30 unasked.  [seq 14]");
    expect(ran.out).toContain("· not judged: the call is still live");
    expect(ran.out).toContain("1 eval · $0.0031 · nothing was written");
  });

  it("try --org is refused: a try is one agent's calls", async () => {
    const ran = await run(["judges", "try", "x", "--last", "3", "--org"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("--agent names it, never --org");
  });
});

describe("pinecall judging", () => {
  it("alone reads it", async () => {
    answer("get", "/v1/org/judging", JUDGING);
    const ran = await run(["judging"]);
    expect(ran.out).toBe("judging on · Pinecall's judge model · evals billed · ceiling $0.05 a call\n");
  });

  it("--agent says a line more: the judge the agent's own settings name, and whose key it runs on", async () => {
    answer("get", "/v1/org/judging", JUDGING);
    const sent = answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, yours: tuningRow("m_1", 4, { judge: "openai/gpt-5.4-mini" }) });
    answer("get", "/v1/provider-keys", { vendors: ["openai"] });
    const ran = await run(["judging", "--agent", "front-desk"]);
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/settings");
    expect(ran.out).toBe("judging on · Pinecall's judge model · evals billed · ceiling $0.05 a call\n  front-desk · judged on openai/gpt-5.4-mini · your own key: evals not billed\n");
  });

  it("--agent on an agent with no judge of its own says its calls are judged as the org's; a class's own wins over both", async () => {
    answer("get", "/v1/org/judging", JUDGING);
    answer("get", "/v1/agents/:slug/settings", SETTINGS);
    answer("get", "/v1/provider-keys", { vendors: [] });
    expect((await run(["judging", "--agent", "front-desk"])).out).toContain("  front-desk · no judge model of its own: its calls are judged as above\n");
    answer("get", "/v1/agents/:slug/settings", { ...SETTINGS, fixed: ["judge"] });
    expect((await run(["judging", "--agent", "front-desk"])).out).toContain("  front-desk · the class declares its own judge model");
  });

  it("without --agent it is the org's line alone, and asks nothing of any agent", async () => {
    answer("get", "/v1/org/judging", JUDGING);
    const asked = answer("get", "/v1/agents/:slug/settings", SETTINGS);
    await run(["judging"]);
    expect(asked).toHaveLength(0);
  });

  it("off is one word, and keeps the model", async () => {
    answer("get", "/v1/org/judging", JUDGING);
    const sent = answer("put", "/v1/org/judging", { ...JUDGING, on: false });
    const ran = await run(["judging", "off"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toEqual({ on: false });
    expect(ran.out).toContain("judging off — no call is judged at hang-up");
  });

  it("--model with --option names a model of the org's own, on its own key", async () => {
    const model = { provider: "openai", model: "qwen3-32b", options: { base_url: "http://gpu.internal:8000/v1" } };
    answer("get", "/v1/org/judging", JUDGING);
    const sent = answer("put", "/v1/org/judging", { ...JUDGING, model });
    answer("get", "/v1/provider-keys", { vendors: ["openai"] });
    const ran = await run(["judging", "--model", "openai/qwen3-32b", "--option", "base_url=http://gpu.internal:8000/v1"]);
    expect(sent[0]!.body).toEqual({ on: true, model });
    expect(ran.out).toBe('judging on · openai/qwen3-32b · base_url="http://gpu.internal:8000/v1" · your own openai key: evals not billed\n');
  });

  it("refuses a word that is not on or off", async () => {
    const ran = await run(["judging", "maybe"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("judging takes on or off, not maybe");
  });

  it("refuses --model beside --platform before asking anything", async () => {
    expect((await run(["judging", "--model", "haiku", "--platform"])).code).toBe(2);
  });
});
