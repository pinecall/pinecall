/** The Test tab's doors: an agent's cases and goldens, the runs that play them, and its callers written, switched and proposed. */

import { z } from "zod";

import { drop, patch, post, put, read, type Credentials } from "@pinecall/core/api";
import { type CaseDecision, type EvalCase, EvalCaseListSchema, EvalCaseSchema, type GeneratedPersonas, GeneratedPersonasSchema, type Persona, PersonaListSchema, type PersonaPut, type ProposedPersona, type WriteCase } from "@pinecall/core/wire/rest-evals";

export type { CaseDecision, EvalCase, GeneratedPersonas, Persona, PersonaPut, ProposedPersona, WriteCase };

const named = encodeURIComponent;

// ── cases: the org's dataset, one agent's; an approved one is a golden ──

export interface Cases {
  cases: EvalCase[];
  /** How many wait for a person to decide. */
  pending: number;
}

export async function readCases(credentials: Credentials, agent: string): Promise<Cases> {
  const listed = EvalCaseListSchema.parse(await read(credentials, "/v1/evals/cases", { agent }));
  return { cases: listed.cases, pending: listed.pending };
}

/** A golden written by hand, approved from the start; the same name again rewrites it, and one a call made is refused. */
export async function writeGolden(credentials: Credentials, agent: string, name: string, body: WriteCase): Promise<EvalCase> {
  return EvalCaseSchema.parse(await put(credentials, `/v1/agents/${named(agent)}/cases/${named(name)}`, body));
}

/** What a person decided of a case: approved, dismissed, held out or not. */
export async function decideCase(credentials: Credentials, id: string, decision: CaseDecision): Promise<EvalCase> {
  return EvalCaseSchema.parse(await patch(credentials, `/v1/evals/cases/${named(id)}`, decision));
}

export async function dropCase(credentials: Credentials, id: string): Promise<void> {
  await drop(credentials, `/v1/evals/cases/${named(id)}`);
}

// ── runs: goldens played against the agent, each judged ──

const ScoreSchema = z.looseObject({ metric: z.string(), passed: z.boolean(), reason: z.string() });
const CellSchema = z.looseObject({ model: z.string(), golden: z.string(), scores: z.array(ScoreSchema) });
const RunSchema = z.looseObject({
  id: z.string(),
  agent: z.string(),
  started_at: z.number(),
  finished_at: z.number().nullable(),
  // `failed` is the run itself breaking; a golden that broke is a score, not a status.
  status: z.enum(["running", "done", "failed"]),
  calls: z.array(z.looseObject({ golden: z.string(), model: z.string(), call: z.string() })),
  matrix: z.looseObject({ goldens: z.array(z.string()), runs: z.array(CellSchema) }).nullable(),
  error: z.string().nullable(),
});
export type Run = z.infer<typeof RunSchema>;

const RunListSchema = z.looseObject({ runs: z.array(RunSchema) });

// The door's own most.
const AS_MANY_AS_IT_GIVES = 200;

/** The agent's runs in this world, newest first. */
export async function readRuns(credentials: Credentials, agent: string): Promise<Run[]> {
  return RunListSchema.parse(await read(credentials, "/v1/evals/runs", { agent, limit: AS_MANY_AS_IT_GIVES })).runs;
}

export async function readRun(credentials: Credentials, id: string): Promise<Run> {
  return RunSchema.parse(await read(credentials, `/v1/evals/runs/${named(id)}`));
}

/** Play the goldens named through whatever holds the agent; answered at once with the run, still running. */
export async function runGoldens(credentials: Credentials, agent: string, cases: readonly string[]): Promise<Run> {
  return RunSchema.parse(await post(credentials, "/v1/evals/run", { agent, cases }));
}

// ── callers: the agent's own, written here, and Pinecall's, switched ──

const callersDoor = (agent: string, name?: string): string => `/v1/agents/${named(agent)}/personas${name === undefined ? "" : `/${named(name)}`}`;

/** Write a caller whole, or rename it from `was`; answers the agent's callers as they stand. */
export async function writeCaller(credentials: Credentials, agent: string, name: string, written: PersonaPut): Promise<Persona[]> {
  return PersonaListSchema.parse(await put(credentials, callersDoor(agent, name), written)).personas;
}

/** One of Pinecall's callers taken into the agent's, or put back. */
export async function switchCaller(credentials: Credentials, agent: string, name: string, on: boolean): Promise<Persona[]> {
  return PersonaListSchema.parse(await put(credentials, callersDoor(agent, name), { on })).personas;
}

export async function dropCaller(credentials: Credentials, agent: string, name: string): Promise<Persona[]> {
  return PersonaListSchema.parse(await drop(credentials, callersDoor(agent, name))).personas;
}

/** Callers a model writes for the agent from its prompt, tools and knowledge; saved nowhere until one is kept. */
export async function proposeCallers(credentials: Credentials, agent: string, about: string): Promise<GeneratedPersonas> {
  return GeneratedPersonasSchema.parse(await post(credentials, `${callersDoor(agent)}/generate`, about.trim() === "" ? {} : { about: about.trim() }));
}
