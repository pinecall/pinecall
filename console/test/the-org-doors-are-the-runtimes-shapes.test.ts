/** Org screens parse the gateway's shapes field for field and reject renamed fields. */

import { expect, test } from "vitest";
import { z } from "zod";

// Schemas are module-private, so they are tested through each door's functions with a stub fetch.
import { readCatalog, readNumbers, readPath } from "../src/screens/numbers/door";
import { readMembers } from "../src/screens/team/door";
import { readUsage } from "../src/screens/usage/door";

const CREDENTIALS = { base: "/", key: "pk_test" };

// runtime log/usage.py: UsageRow and Totals, as asdict() writes them.
const A_USAGE_PAGE = {
  rows: [
    { cursor: 7, org: "clinica", agent: "clinica-norte", call: "CA_1", type: "call.summary", at: 1.5, minutes: 1.5, messages: 6, input_tokens: 1200, output_tokens: 300, characters: 0, judge_calls: 0, evals: 0, simulated: true, cost_usd: 0.0021 },
  ],
  totals: { minutes: 1.5, messages: 6, input_tokens: 1200, output_tokens: 300, characters: 0, judge_calls: 0, evals: 0, simulations: 1, cost_usd: 0.0021, calls: 1 },
  next: 7,
};

// runtime api/routes.py: `Answering` — the domain's Route and which table put it there.
const A_DOOR = { route: { org: "clinica", agent: "clinica-norte", channel: "phone", number: "+34910000000", env: "production" } };

// runtime api/members.py: one member as the wire says it.
const A_MEMBER = { id: "m_1", email: "ana@clinica.uy", name: "Ana", role: "supervisor", agents: ["clinica-norte"], status: "active", scopes: ["calls", "evals", "supervise", "talk"], production: true };

function answering(body: unknown): void {
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async () => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } })) as typeof fetch;
}

test("usage is the runtime's rows and totals, field for field", async () => {
  answering(A_USAGE_PAGE);
  const page = await readUsage(CREDENTIALS);
  expect(page.totals?.calls).toBe(1);
  expect(page.rows[0]?.cost_usd).toBe(0.0021);
  expect([page.rows[0]?.simulated, page.totals?.simulations, page.totals?.evals]).toEqual([true, 1, 0]);
  answering({ ...A_USAGE_PAGE, rows: [{ ...A_USAGE_PAGE.rows[0], minutes: undefined }] });
  await expect(readUsage(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

test("a number is a route, and a member is who they are with what their role opens", async () => {
  answering([A_DOOR]);
  expect((await readNumbers(CREDENTIALS))[0]?.route.agent).toBe("clinica-norte");
  answering({ members: [A_MEMBER] });
  expect((await readMembers(CREDENTIALS))[0]?.scopes).toContain("supervise");
  expect((await readMembers(CREDENTIALS))[0]?.production).toBe(true);
  answering({ members: [{ ...A_MEMBER, role: "owner" }] });
  await expect(readMembers(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

// runtime wire/rest/numbers.py: NumberRow with what a call to it does, NumberPath, CarrierCatalog.
const A_ROW = { ...A_DOOR, origin: "typed", rings: "waiting", last_call_at: null, via: "telnyx", account: null };
const A_PATH = {
  number: "+34910000000",
  steps: [
    { step: "carrier", state: "waiting", says: "Waiting for the first call to +34910000000", fix: null },
    { step: "fence", state: "ok", says: "Admitted from Telnyx's networks", fix: null },
    { step: "world", state: "ok", says: "The production rule sends it to the production fleet", fix: null },
    { step: "agent", state: "broken", says: "Nobody runs clinica-norte in the production", fix: "Run pinecall start in the agent's folder, or deploy it" },
  ],
  rings: "broken",
  last_call_at: null,
};
const A_CATALOG = { carriers: [{ kind: "twilio", name: "Twilio", how: "automatic", networks: ["54.172.60.0/30"] }], sells: false };

test("a number says who wrote it and what a call to it does, its path says why, and the catalog what may be added", async () => {
  answering([A_ROW]);
  const [row] = await readNumbers(CREDENTIALS);
  expect([row?.origin, row?.rings, row?.via]).toEqual(["typed", "waiting", "telnyx"]);
  answering(A_PATH);
  expect((await readPath(CREDENTIALS, "+34910000000")).steps.map((step) => step.state)).toEqual(["waiting", "ok", "ok", "broken"]);
  answering(A_CATALOG);
  expect((await readCatalog(CREDENTIALS)).carriers[0]?.how).toBe("automatic");
  answering({ ...A_PATH, steps: [{ ...A_PATH.steps[0], state: "fine" }] });
  await expect(readPath(CREDENTIALS, "+34910000000")).rejects.toBeInstanceOf(z.ZodError);
});

// runtime api/numbers.py and api/managed.py: carrier, owned numbers, and the import/purchase answer.
test("the numbers screen parses the carrier, the account's numbers and a plan, and refuses a step that is not a string", async () => {
  const { readCarriers, readAvailable, importNumber, buyNumber } = await import("../src/screens/numbers/door");
  answering({ carriers: [{ kind: "twilio", account: "AC" + "0".repeat(32) }, { kind: "whatsapp", account: "1055", label: "Clínica" }] });
  expect((await readCarriers(CREDENTIALS)).map((one) => one.kind)).toEqual(["twilio", "whatsapp"]);
  answering({ kind: "twilio", numbers: [{ number: "+14176743169", name: "front desk", imported: false }] });
  expect((await readAvailable(CREDENTIALS)).numbers[0]?.imported).toBe(false);
  const wired = { route: { ...A_DOOR.route, channel: "phone", number: "+14176743169", managed: true }, steps: ["buy      +14176743169 — on account AC…, billed to the box"], dry_run: true };
  answering(wired);
  expect((await buyNumber(CREDENTIALS, { country: "US", agent: "clinica-norte", channel: "phone" }, true)).route.managed).toBe(true);
  answering({ ...wired, dry_run: false, route: { ...wired.route, managed: false } });
  expect((await importNumber(CREDENTIALS, { number: "+14176743169", agent: "clinica-norte", channel: "phone" }, false)).dry_run).toBe(false);
  answering({ ...wired, steps: [42] });
  await expect(buyNumber(CREDENTIALS, { country: "US", agent: "clinica-norte", channel: "phone" }, true)).rejects.toBeInstanceOf(z.ZodError);
});

test("an org with no account has none, not a refusal: the door's 404 is the empty state", async () => {
  const { readCarriers } = await import("../src/screens/numbers/door");
  globalThis.fetch = (async () => new Response(JSON.stringify({ detail: "this org has no carrier yet" }), { status: 404, headers: { "content-type": "application/json" } })) as typeof fetch;
  expect(await readCarriers(CREDENTIALS)).toEqual([]);
});

// runtime api/persona_runs.py: one simulation as `_a_row` writes it, off the call index.
const A_RUN = {
  call: "call_9f2a",
  agent: "clinica-norte",
  persona: "office-manager",
  started_at: 1789897543.33,
  ended_at: 1789897601.1,
  turns: 6,
  end_reason: "caller_hung_up",
  outcome: "Le confirmé el turno del jueves a las diez.",
  cost_usd: 0.0069,
  score: { held: 3, judged: 4, passed: false, reason: "never read the address back" },
};

test("the runs pane asks one agent's caller's door, pages with the gateway's own cursor, and parses a run whole", async () => {
  const { readRuns } = await import("../src/screens/personas/door");
  const asked: string[] = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (door: URL) => {
    asked.push(door.toString());
    return new Response(JSON.stringify({ runs: [A_RUN], total: 21, next: "call_older" }), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;

  const page = await readRuns(CREDENTIALS, "front desk", "office manager");
  expect(page.total).toBe(21);
  expect(page.runs[0]?.score?.passed).toBe(false);
  await readRuns(CREDENTIALS, "front desk", "office manager", { before: page.next ?? undefined });
  expect(asked).toEqual([
    "https://cloud.pinecall.io/v1/agents/front%20desk/personas/office%20manager/runs",
    "https://cloud.pinecall.io/v1/agents/front%20desk/personas/office%20manager/runs?before=call_older",
  ]);

  answering({ runs: [{ ...A_RUN, turns: "six" }], total: 1, next: null });
  await expect(readRuns(CREDENTIALS, "front-desk", "office-manager")).rejects.toBeInstanceOf(z.ZodError);
});

// runtime gateway/api/personas.py: PersonaList, one agent's callers.
const A_PERSONA = {
  agent: "front-desk",
  name: "office-manager",
  about: "",
  goal: "move the Thursday appointment",
  style: "brisk",
  facts: {},
  state: {},
  llm: null,
  tts: null,
  voice: null,
  owner: "front-desk",
  on: true,
  expects: ["The agent should take the message."],
  tags: [],
  behavior: { interrupts: 0, pause_s: 0, interferer_db: null, packet_loss: 0, backchannels: 0, speed: 1, ambience: "television" },
  author: "m_ana",
  set_at: 1790000000,
};

test("the personas list asks the agent's own door, and a row naming agents is not the runtime's shape", async () => {
  const { readPersonas } = await import("../src/screens/personas/door");
  const asked: string[] = [];
  globalThis.fetch = (async (door: URL) => {
    asked.push(door.toString());
    return new Response(JSON.stringify({ personas: [A_PERSONA] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;

  expect((await readPersonas(CREDENTIALS, "front-desk"))[0]?.name).toBe("office-manager");
  expect(asked).toEqual(["https://cloud.pinecall.io/v1/agents/front-desk/personas"]);

  answering({ personas: [{ ...A_PERSONA, agents: ["front-desk"] }] });
  await expect(readPersonas(CREDENTIALS, "front-desk")).rejects.toBeInstanceOf(z.ZodError);
});

// runtime gateway/api/personas.py: every agent's callers and every simulated call, each row saying whose.
test("the org's harness asks the org's own doors: every caller by agent, and the simulations — every agent's or one's — paged by the cursor", async () => {
  const { readEveryPersona, readSimulations } = await import("../src/screens/personas/door");
  const asked: string[] = [];
  globalThis.fetch = (async (door: URL) => {
    asked.push(door.toString());
    const said = door.pathname === "/v1/personas" ? { personas: [A_PERSONA] } : { runs: [A_RUN], total: 2, next: "call_9f2a" };
    return new Response(JSON.stringify(said), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;

  expect((await readEveryPersona(CREDENTIALS))[0]?.agent).toBe("front-desk");
  const page = await readSimulations(CREDENTIALS, ["pinecall", "bernardo"]);
  expect(page.runs[0]?.persona).toBe("office-manager");
  await readSimulations(CREDENTIALS, ["pinecall", "bernardo"], page.next ?? undefined);
  await readSimulations(CREDENTIALS, ["clinica-norte"]);
  expect(asked).toEqual([
    "https://cloud.pinecall.io/v1/personas",
    "https://cloud.pinecall.io/v1/simulations?agent=pinecall&agent=bernardo",
    "https://cloud.pinecall.io/v1/simulations?agent=pinecall&agent=bernardo&before=call_9f2a",
    "https://cloud.pinecall.io/v1/simulations?agent=clinica-norte",
  ]);
});

// runtime api/voices.py: VoicesListed, and a WAV sample with vendor timings in Server-Timing.
const MARTA = { id: "de38f545-c574-44e8-9b54-a7d6fec1c6b1", name: "Marta - Friendly Guide", language: "es", description: "Approachable Spanish female.", gender: "feminine", country: "ES", accent: "castilian" };

test("the voice picker parses the vendor's voices as the wire says them, and refuses a field renamed", async () => {
  const { readVoices } = await import("../src/screens/settings/voice-doors");
  answering({ tts: "cartesia", language: "es", voices: [MARTA] });
  expect((await readVoices(CREDENTIALS, "cartesia", "es"))[0]?.country).toBe("ES");
  answering({ tts: "cartesia", language: "es", voices: [{ ...MARTA, country: undefined, region: "ES" }] });
  await expect(readVoices(CREDENTIALS, "cartesia", "es")).rejects.toBeInstanceOf(z.ZodError);
});

test("a sample is the WAV handed to the player as a blob, with the vendor's wait read off Server-Timing", async () => {
  const { heard } = await import("../src/screens/settings/voice-doors");
  const sent: { url: string; body: string; type: string | null }[] = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (door: URL, init?: RequestInit) => {
    sent.push({ url: door.toString(), body: String(init?.body), type: new Headers(init?.headers).get("content-type") });
    return new Response(new Uint8Array([82, 73, 70, 70]), { status: 200, headers: { "content-type": "audio/wav", "server-timing": "first-audio;dur=271, total;dur=955" } });
  }) as unknown as typeof fetch;

  const said = await heard(CREDENTIALS, { tts: "cartesia", voice: MARTA.id, model: "sonic-3", language: "es" });

  expect(said.firstAudioMs).toBe(271);
  expect(said.url.startsWith("blob:")).toBe(true);
  URL.revokeObjectURL(said.url);
  expect(sent[0]?.url).toBe("https://cloud.pinecall.io/v1/voices/sample");
  expect(sent[0]?.type).toBe("application/json");
  expect(JSON.parse(sent[0]!.body)).toEqual({ tts: "cartesia", voice: MARTA.id, model: "sonic-3", language: "es" });
});

// runtime gateway/api/judges.py: JudgeList, as every one of the doors answers it — Pinecall's first, then the org's own.
const LIBRARY_JUDGE = { name: "consent", owner: "pinecall", on: true, question: "…", answer: "verdict", choices: [], when: "always", trigger: "", reads: ["facts"], summary: "Every irreversible tool ran after a yes.", version: 1, why: "Stops a booking nobody agreed to.", recommended: true };
const A_JUDGE = { name: "offers-next-slot", owner: "clinica-norte", on: true, question: "The agent offered the next free slot.", answer: "verdict", choices: [], when: "always", trigger: "", reads: [], author: "m_ana", set_at: 1789897543.33, recommended: false };

test("an agent's judges are read, written, switched and dropped at the agent's door, and the old shape is refused", async () => {
  const { dropJudge, readJudges, writeJudge } = await import("../src/screens/quality/judges-door");
  const asked: { method: string; url: string; body: string | undefined }[] = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (door: URL, init?: RequestInit) => {
    asked.push({ method: init?.method ?? "GET", url: door.toString(), body: init?.body === undefined ? undefined : String(init.body) });
    return new Response(JSON.stringify({ judges: [LIBRARY_JUDGE, A_JUDGE] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;

  expect((await readJudges(CREDENTIALS, "clinica-norte")).map((judge) => judge.owner)).toEqual(["pinecall", "clinica-norte"]);
  await writeJudge(CREDENTIALS, "clinica-norte", "offers-next-slot", { question: A_JUDGE.question, answer: "choice", choices: ["offered", "not offered"], when: "simulations", reads: ["prompt"] });
  await writeJudge(CREDENTIALS, "clinica-norte", "consent", { on: false });
  await dropJudge(CREDENTIALS, "clinica-norte", "offers-next-slot");
  expect(asked.map(({ method, url }) => `${method} ${url}`)).toEqual([
    "GET https://cloud.pinecall.io/v1/agents/clinica-norte/judges",
    "PUT https://cloud.pinecall.io/v1/agents/clinica-norte/judges/offers-next-slot",
    "PUT https://cloud.pinecall.io/v1/agents/clinica-norte/judges/consent",
    "DELETE https://cloud.pinecall.io/v1/agents/clinica-norte/judges/offers-next-slot",
  ]);
  expect(JSON.parse(asked[2]?.body ?? "{}")).toEqual({ on: false });

  answering({ judges: [{ ...A_JUDGE, when: "sometimes" }] });
  await expect(readJudges(CREDENTIALS, "clinica-norte")).rejects.toBeInstanceOf(z.ZodError);
  answering({ judges: [{ name: A_JUDGE.name, question: A_JUDGE.question, runs_on: "every-call", author: "m_ana", set_at: 1 }] });
  await expect(readJudges(CREDENTIALS, "clinica-norte")).rejects.toBeInstanceOf(z.ZodError);
});

test("the org's judges are read, written and dropped at the org's door, the same shape as an agent's", async () => {
  const { dropJudge, readJudges, writeJudge } = await import("../src/screens/quality/judges-door");
  const asked: { method: string; url: string }[] = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (door: URL, init?: RequestInit) => {
    asked.push({ method: init?.method ?? "GET", url: door.toString() });
    return new Response(JSON.stringify({ judges: [LIBRARY_JUDGE, { ...A_JUDGE, owner: "org" }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;
  expect((await readJudges(CREDENTIALS, null))[1]?.owner).toBe("org");
  await writeJudge(CREDENTIALS, null, "never-medical-advice", { question: "No medical advice." });
  await dropJudge(CREDENTIALS, null, "never-medical-advice");
  expect(asked.map(({ method, url }) => `${method} ${url}`)).toEqual([
    "GET https://cloud.pinecall.io/v1/org/judges",
    "PUT https://cloud.pinecall.io/v1/org/judges/never-medical-advice",
    "DELETE https://cloud.pinecall.io/v1/org/judges/never-medical-advice",
  ]);
});

// runtime gateway/api/judges.py try_judge: JudgeTried, nothing written.
test("a judge is tried on the agent's last calls by its name or written whole, and each call's answer comes back", async () => {
  const { tryJudge } = await import("../src/screens/quality/judges-door");
  const sent: { url: string; body: unknown }[] = [];
  globalThis.fetch = (async (door: URL, init?: RequestInit) => {
    sent.push({ url: door.toString(), body: JSON.parse(String(init?.body ?? "null")) });
    const judgment = { name: "consent", verdict: "na", criteria: "…", reason: "no irreversible tool ran", evidence: { seqs: [] } };
    return new Response(JSON.stringify({ rows: [{ call: "call_1", judgment }, { call: "call_2", judgment: null, not_judged: "the call has not finished" }], evals: 0, cost_usd: 0 }), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;

  const tried = await tryJudge(CREDENTIALS, "clinica-norte", { name: "consent", last: 2 });
  expect(tried.rows.map((row) => row.judgment?.verdict ?? row.not_judged)).toEqual(["na", "the call has not finished"]);
  expect(sent).toEqual([{ url: "https://cloud.pinecall.io/v1/agents/clinica-norte/judges/try", body: { name: "consent", last: 2 } }]);
});

// runtime gateway/api/org.py: JudgingSettings, the model kept as the org named it.
test("judging is read and written whole with the model it runs on, null being Pinecall's", async () => {
  const { readJudging, writeJudging } = await import("../src/screens/quality/judges-door");
  const local = { provider: "openai", model: "qwen3-32b", options: { base_url: "http://gpu:8000/v1" } };
  const sent: { method: string; body: unknown }[] = [];
  globalThis.fetch = (async (_door: URL, init?: RequestInit) => {
    sent.push({ method: init?.method ?? "GET", body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) });
    return new Response(JSON.stringify({ on: true, ceiling_usd: 0.05, model: local }), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;

  expect((await readJudging(CREDENTIALS)).model).toEqual(local);
  await writeJudging(CREDENTIALS, { on: true, model: null });
  expect(sent[1]).toEqual({ method: "PUT", body: { on: true, model: null } });
  answering({ on: true, ceiling_usd: null, model: { vendor: "openai" } });
  await expect(readJudging(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

// runtime gateway/api/simulations.py: the gateway plays the persona against whoever holds the agent.
test("a simulation is asked of the gateway by the persona's name, and its call comes back at once", async () => {
  const { startSimulation } = await import("../src/screens/simulations/simulating");
  const sent: { url: string; body: unknown }[] = [];
  globalThis.fetch = (async (door: URL, init?: RequestInit) => {
    sent.push({ url: door.toString(), body: JSON.parse(String(init?.body ?? "null")) });
    return new Response(JSON.stringify({ call: "call_9f2a", voice: true }), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;

  const call = await startSimulation(CREDENTIALS, { agent: "bernardo", persona: "cto-books-a-call", voice: true, turns: 15 });
  expect(call).toBe("call_9f2a");
  expect(sent).toEqual([{ url: "https://cloud.pinecall.io/v1/simulations", body: { agent: "bernardo", persona: "cto-books-a-call", voice: true, turns: 15 } }]);
  answering({ call: "call_9f2a" });
  await expect(startSimulation(CREDENTIALS, { agent: "bernardo", persona: "x", voice: false, turns: 2 })).rejects.toBeInstanceOf(z.ZodError);
});
