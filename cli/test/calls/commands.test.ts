/** `pinecall sessions | data` as typed: the list, one call by its id alone, its log with where to read on; erasures that need --yes. */

import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import { answer, GATEWAY, server } from "../support/gateway.js";
import { folder } from "../support/project.js";
import { run } from "../support/run.js";

const A_CALL = {
  call: "call_df5aaa81ac7142f5a2c6f9b77033d23e",
  agent: "front-desk",
  live: false,
  last_seq: 48,
  status: "ended",
  channel: "web",
  direction: "inbound",
  from: null,
  to: null,
  caller: null,
  started_at: 1_792_150_000,
  ended_at: 1_792_150_031,
  end_reason: "caller_hung_up",
  outcome: "Clínica Norte, good morning",
  cost: null,
};

describe("pinecall sessions", () => {
  it("alone lists the agent's calls; --agent reads a slug from any folder", async () => {
    const sent = answer("get", "/v1/agents/:slug/sessions", { calls: [A_CALL] });
    const ran = await run(["sessions", "--agent", "sales", "--limit", "3"], { cwd: folder() });
    expect(ran.code).toBe(0);
    expect(sent[0]!.path).toBe("/v1/agents/sales/sessions");
    expect(sent[0]!.query).toEqual({ limit: "3" });
    expect(ran.out).toContain("call_df5aaa81ac7142f5a2c6f9b77033d23e");
  });

  it("<call> shows that call whole: outcome, how it ended, the score", async () => {
    answer("get", "/v1/calls/:call/state", { live: false, last_seq: 48 });
    answer("get", "/v1/calls/:call/events", {
      entries: [
        { seq: 46, type: "call.summary", data: { outcome: "Booked Thursday at ten.", reason: "caller_hung_up", duration_s: 84, turns: 4 } },
        { seq: 47, type: "call.score", data: { passed: true, judges: [{ name: "grounded", verdict: "held", criteria: "", reason: "" }], judge_calls: 1, evals: 1 } },
      ],
      next: null,
    });
    const ran = await run(["sessions", "call_5b1f"]);
    expect(ran.code).toBe(0);
    expect(ran.out).toContain("  outcome   Booked Thursday at ten.");
    expect(ran.out).toContain("  ended     caller_hung_up · 1m 24s · 4 turns");
    expect(ran.out).toContain("✓ every judge held · 1 judges · 1 model call · 1 eval");
  });

  it("<call> an id the gateway does not know is refused by name", async () => {
    server.use(http.get(`${GATEWAY}/v1/calls/:call/state`, () => HttpResponse.json({ detail: "no such call" }, { status: 404 })));
    const ran = await run(["sessions", "call_typo"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("no call call_typo on this gateway: `pinecall sessions` names the ones there are");
  });

  it("show and list are no verbs of it any more", async () => {
    expect((await run(["sessions", "show", "call_1"])).code).toBe(2);
  });

  it("log prints an entry a line and the line that reads on", async () => {
    answer("get", "/v1/calls/:call/state", { live: false, last_seq: 120 });
    answer("get", "/v1/calls/:call/events", {
      entries: [
        { seq: 41, ts: 1_792_150_442.31, type: "turn.user", data: { text: "Thursday at ten, if Dr. Vidal has it." } },
        { seq: 42, ts: 1_792_150_442.311, type: "agent.state", data: { state: "thinking" } },
      ],
      next: 42,
    });
    const ran = await run(["sessions", "log", "call_5b1f", "--after", "40", "--types", "turn.user,agent.state"]);
    expect(ran.out).toMatch(/^ {4}41 {2}\d{2}:\d{2}:\d{2}\.\d{3} {2}turn\.user {4}Thursday at ten, if Dr\. Vidal has it\.\n/);
    expect(ran.out).toContain("more: pinecall sessions log call_5b1f --after 42");
  });

  it("log refuses a cursor that is no number", async () => {
    expect((await run(["sessions", "log", "call_1", "--after", "end"])).err).toContain("--after takes a number, not end");
  });
});

describe("pinecall data", () => {
  it("erase is refused without --yes, and nothing is sent", async () => {
    const ran = await run(["data", "erase", "call", "call_1"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("erasing call call_1 cannot be undone: run it again with --yes");
  });

  it("erase contact --yes says what went", async () => {
    const sent = answer("delete", "/v1/contacts/:contact", { id: 1, at: 1_792_150_000, what: "contact", subject: "+34600000001", env: "sandbox", asked_by: "m_ana", calls: 3, entries: 210, memories: 4, recordings: 2 });
    const ran = await run(["data", "erase", "contact", "+34600000001", "--yes"]);
    expect(sent[0]!.path).toBe("/v1/contacts/%2B34600000001");
    expect(ran.out).toContain("contact +34600000001  3 call(s), 210 entries, 4 memories, 2 recording(s)  by m_ana");
  });

  it("policy --no-disclosure and --calling-hours change their fields", async () => {
    const row = { policy: { retention_days: null, calling_hours: null, per_number_day: null, consent_everywhere: false, disclosure: null, recording_notice: true }, set_by: null, set_at: null };
    answer("get", "/v1/org/policy", row);
    const sent = answer("put", "/v1/org/policy", { ...row, policy: { ...row.policy, calling_hours: { from: 9, until: 20 }, disclosure: "" } });
    const ran = await run(["data", "policy", "--calling-hours", "9-20", "--no-disclosure"]);
    expect(ran.code).toBe(0);
    expect(sent[0]!.body).toMatchObject({ calling_hours: { from: 9, until: 20 }, disclosure: "" });
    expect(ran.out).toContain("a number is rung from 9:00 to 20:00 of its own day");
  });

  it("dnc add needs --source", async () => {
    expect((await run(["data", "dnc", "add", "+15550001"])).code).toBe(2);
  });

  it("export with no --out streams the JSON Lines to stdout", async () => {
    server.use(http.get(`${GATEWAY}/v1/org/export`, () => new HttpResponse('{"type":"call"}\n', { headers: { "content-type": "application/x-ndjson" } })));
    const ran = await run(["data", "export"]);
    expect(ran.code).toBe(0);
    expect(ran.out).toBe('{"type":"call"}\n');
  });
});
