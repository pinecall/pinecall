/** What the gateway answers, as the tests of a service and of its verbs both need it: one shape each, written once. */

const free = { limit: null, used: 0 };

/** `GET /v1/limits` in the sandbox. */
export const LIMITS = {
  minutes: { limit: 30, used: 12 },
  messages: free,
  llm_tokens: { limit: 1_000_000, used: 20_500.5 },
  concurrent_calls: { limit: 2, used: 0 },
  agents: { limit: 3, used: 1 },
  seats: free,
  numbers: { limit: 0, used: 0 },
  evals: { limit: 100, used: 40 },
  simulations: free,
  memory_facts: { limit: 500, used: 12 },
  knowledge_chunks: { limit: 2000, used: 340 },
  hosted_apps: { limit: 3, used: 1 },
  budget_usd: { limit: 60, used: 4.25 },
  lends: ["google", "cartesia", "deepgram"] as string[] | null,
  billing_url: null as string | null,
  world: "sandbox",
};

/** `GET /v1/providers`. */
export const CATALOG = {
  providers: [
    { name: "anthropic", does: ["llm"], standing: "ready", env: "ANTHROPIC_API_KEY", aliases: ["claude"] },
    { name: "cartesia", does: ["stt", "tts"], standing: "no key", env: "CARTESIA_API_KEY", aliases: [] },
    { name: "deepgram", does: ["stt"], standing: "ready", env: "DEEPGRAM_API_KEY", aliases: ["dg"] },
  ],
  defaults: { llm: "anthropic", stt: "deepgram", tts: "cartesia" },
};

/** One judge of the agent's own, as `GET …/judges` lists it. */
export const A_JUDGE = {
  name: "offers-next-slot",
  owner: "front-desk",
  on: true,
  question: "The agent offered the next free slot before the caller asked twice.",
  answer: "verdict" as const,
  choices: [] as string[],
  when: "always" as const,
  trigger: "",
  reads: [] as ("prompt" | "evidence" | "facts")[],
  recommended: false,
};

/** One of Pinecall's library judges, off and recommended. */
export const A_LIBRARY_JUDGE = { ...A_JUDGE, name: "consent", owner: "pinecall", on: false, question: "The caller consented to being recorded.", recommended: true };

/** `GET /v1/org/judging` on Pinecall's model. */
export const JUDGING = { on: true, ceiling_usd: 0.05, model: null };

/** One version of a settings corner. */
export function tuningRow(holder: string, version: number, config: Record<string, unknown>) {
  return { holder, version, author: "ana@clinica.test", note: null, set_at: 1_792_150_000, config };
}

/** `GET …/settings` for a person in the sandbox: nothing of their own yet, the team's v3, production's v7. */
export const SETTINGS = {
  world: "sandbox" as const,
  yours: null as ReturnType<typeof tuningRow> | null,
  team: tuningRow("", 3, { voice: "cartesia-ana", llm: "anthropic/claude-haiku-5-5", turn: { endpointing_ms: 400 }, greeting: { say: "Clínica Norte, good morning" }, memory: { remember: ["the caller's name"], forget: [] } }),
  production: tuningRow("", 7, { voice: "cartesia-ana" }),
  fixed: [] as string[],
};

/** One version of a lexicon corner. */
export function lexiconRow(holder: string, version: number, said: { word: string; spoken: string }[], heard: string[]) {
  return { holder, version, author: "ana@clinica.test", note: null, set_at: 1_792_150_000, lexicon: { said, heard } };
}

/** A suite run that finished: one golden under the agent's own model, held unless a score says otherwise. */
export function aRun(scores: { metric: string; passed: boolean; reason?: string }[] = [{ metric: "tools", passed: true }], id = "run_1") {
  const cell = { model: "declared", golden: "books-thursday", scores: scores.map((one) => ({ score: one.passed ? 1 : 0, criteria: "", judge_calls: 0, reason: "", ...one })), summary: { duration_s: 31, turns: 4 }, asked: null };
  const failures = scores.filter((one) => !one.passed).map((one) => ({ model: "declared", golden: "books-thursday", metric: one.metric }));
  return {
    id,
    agent: "front-desk",
    started_at: 1_792_150_000,
    finished_at: 1_792_150_040,
    status: "done" as "running" | "done" | "failed",
    calls: [{ golden: "books-thursday", model: "declared", call: "call_g1" }],
    matrix: { models: ["declared"], goldens: ["books-thursday"], metrics: scores.map((one) => one.metric), judge_calls: 0, runs: [cell], failures },
    error: null as string | null,
  };
}

/** A persona of the agent's own, as its list carries it. */
export const A_PERSONA = {
  name: "apurado",
  owner: "front-desk",
  on: true,
  about: "",
  goal: "book the first slot tomorrow",
  style: "short, impatient",
  facts: { name: "Luis" } as Record<string, string>,
  state: {},
  llm: null as string | null,
  tts: null as string | null,
  voice: null as string | null,
  expects: [] as string[],
  tags: [] as string[],
  behavior: { interrupts: 0.3, pause_s: 0.5, interferer_db: null as number | null, packet_loss: 0, backchannels: 0, speed: 1, ambience: "" },
};

/** One case of the agent's dataset, as the gateway sends it, defaults left out. */
export const A_CASE = {
  id: "case_1",
  agent: "front-desk",
  name: "double-booked",
  golden: { name: "double-booked", turns: [{ say: "I need Thursday." }], expect: { not_tools: ["book"] } },
  source_call: "call_9",
  source_env: "production" as const,
  held_out: false,
  author: "ana@clinica.test",
  created_at: 1_792_150_000,
  status: "pending" as const,
};
