/** Cases parse the gateway's shapes field for field, a golden as turns, and a decision is a PATCH. */

import { expect, test } from "vitest";
import { z } from "zod";

import { decideCase, decideGroup, keepCall, readCases, readGroups, writeCase } from "../src/screens/cases/door";

const CREDENTIALS = { base: "/", key: "pk_test" };

// runtime wire/rest/evals.py: EvalCase as the seal keeps a call a judge broke on (evals/dataset.py).
const A_CASE = {
  id: "case_3f0c1a2b4c5d",
  agent: "clinica-norte",
  name: "promises-me-llaman-manana-por-29d7c7",
  golden: {
    name: "promises-me-llaman-manana-por-29d7c7",
    state: { stage: "book" },
    turns: [{ say: "¿Me llaman mañana, por favor?" }, { event: { name: "slot_freed", data: { at: "10:15" } } }],
    memory: ["Prefiere mañanas"],
    today: "2026-10-08",
    expect: { judges: ["promises"] },
    promoted_from: "call_29d7c7",
  },
  source_call: "call_29d7c7",
  source_env: "production",
  held_out: false,
  author: "the hang-up panel",
  created_at: 1791460000.5,
  status: "pending",
  broke: [{ judge: "promises", reason: "it promised a call back and no tool booked one" }],
  source_version: 4,
  kept_in_repo: false,
  decided_by: null,
};

const asked: { method: string; url: string; body: unknown }[] = [];

function answering(body: unknown): void {
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (url: URL, init?: RequestInit) => {
    asked.push({ method: init?.method ?? "GET", url: String(url), body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) });
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
}

test("an agent's cases are the runtime's rows, and a renamed field is refused", async () => {
  answering({ cases: [A_CASE], pending: 1, pending_at_most: 50 });
  const listed = await readCases(CREDENTIALS, "clinica-norte");
  expect(listed.pending).toBe(1);
  expect(listed.pendingAtMost).toBe(50);
  expect(listed.cases[0]?.broke[0]?.judge).toBe("promises");
  expect(listed.cases[0]?.golden.turns?.[1]?.event?.name).toBe("slot_freed");
  expect(asked.at(-1)?.url).toContain("agent=clinica-norte");
  answering({ cases: [{ ...A_CASE, status: "waiting" }], pending: 1, pending_at_most: 50 });
  await expect(readCases(CREDENTIALS, "clinica-norte")).rejects.toBeInstanceOf(z.ZodError);
});

test("a golden is turns: the caller's lines of before are refused, and so is an event that takes steps", async () => {
  answering({ cases: [{ ...A_CASE, golden: { ...A_CASE.golden, turns: undefined, input: ["¿Me llaman?"] } }], pending: 1, pending_at_most: 50 });
  await expect(readCases(CREDENTIALS, "clinica-norte")).rejects.toBeInstanceOf(z.ZodError);
  const stepped = { event: { name: "slot_freed" }, then: [{ reply: { intent: "mentions the slot" } }] };
  answering({ cases: [{ ...A_CASE, golden: { ...A_CASE.golden, turns: [stepped] } }], pending: 1, pending_at_most: 50 });
  await expect(readCases(CREDENTIALS, "clinica-norte")).rejects.toBeInstanceOf(z.ZodError);
});

test("a decision is a PATCH of the case by its id, and keeping a call is a POST naming it", async () => {
  answering({ ...A_CASE, status: "dismissed", decided_by: "m_ana" });
  const decided = await decideCase(CREDENTIALS, A_CASE.id, { status: "dismissed", judge_was_wrong: "promises" });
  expect(decided.status).toBe("dismissed");
  expect(asked.at(-1)).toMatchObject({ method: "PATCH", body: { status: "dismissed", judge_was_wrong: "promises" } });
  expect(asked.at(-1)?.url).toContain(`/v1/evals/cases/${A_CASE.id}`);
  answering({ ...A_CASE, status: "approved", author: "m_ana", broke: [] });
  await keepCall(CREDENTIALS, "call_29d7c7", "kept-29d7c7");
  expect(asked.at(-1)).toMatchObject({ method: "POST", body: { call: "call_29d7c7", name: "kept-29d7c7" } });
});

test("a case written by hand is a PUT under the agent by its name, and comes back a person's with no call", async () => {
  const golden = { name: "no-dice-un-precio", turns: [{ say: "¿Cuánto cuesta una resonancia?" }], expect: { not: ["€"], grounded: true } };
  answering({ ...A_CASE, name: golden.name, golden, source_call: "", author: "m_ana", status: "approved", broke: [], source_version: null, source: "person" });
  const written = await writeCase(CREDENTIALS, "clinica-norte", golden.name, { golden, held_out: false });
  expect(written.source).toBe("person");
  expect(asked.at(-1)).toMatchObject({ method: "PUT", body: { golden, held_out: false } });
  expect(asked.at(-1)?.url).toContain("/v1/agents/clinica-norte/cases/no-dice-un-precio");
});

// runtime wire/rest/evals.py: CaseGroup, as evals/groups.py keeps the cases one judge broke on.
const A_GROUP = {
  id: "grp_4c81e2a07d1b",
  agent: "clinica-norte",
  judge: "promises",
  cause: "The agent promises call backs no tool books.",
  status: "pending",
  since: 1791460000.5,
  cases: 4,
  simulations: 1,
  proposal: { cause: "The agent promises call backs no tool books.", kind: "code", where: "book_callback", change: "call book_callback first", confidence: 0.82 },
  proposed_at: 1791463600.0,
};

test("the groups are the runtime's rows, and a group is decided whole with a PATCH", async () => {
  asked.length = 0;
  answering({ groups: [A_GROUP] });
  const [group] = await readGroups(CREDENTIALS, "clinica-norte");
  expect(group?.proposal?.kind).toBe("code");
  expect(asked[0]?.url).toContain("/v1/evals/groups?agent=clinica-norte");
  answering({ ...A_GROUP, status: "dismissed", proposal: null });
  const decided = await decideGroup(CREDENTIALS, A_GROUP.id, { status: "dismissed", judge_was_wrong: true });
  expect(decided.status).toBe("dismissed");
  expect(asked.at(-1)).toMatchObject({ method: "PATCH", url: expect.stringContaining(`/v1/evals/groups/${A_GROUP.id}`), body: { status: "dismissed", judge_was_wrong: true } });
  answering({ groups: [{ ...A_GROUP, cases: "four" }] });
  await expect(readGroups(CREDENTIALS, "clinica-norte")).rejects.toBeInstanceOf(z.ZodError);
});

