/** Personas doors: CRUD for an agent's synthetic callers and their runs, and the org's every caller and every run. */

import {
  type GeneratedPersonas,
  GeneratedPersonasSchema,
  type Persona,
  PersonaListSchema,
  type PersonaPut,
  type PersonaRun,
  type PersonaRunList,
  PersonaRunListSchema,
  type ProposedPersona,
} from "@pinecall/core/wire/rest-evals";

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";
import { dev } from "../../lib/dev";

export type { GeneratedPersonas, Persona, PersonaRun, ProposedPersona };

/** Whether a caller of the list is Pinecall's: switched on or off, never written or dropped. */
export const isPinecalls = (persona: Persona): boolean => persona.owner === "pinecall";

/** Whether the agent's class owns its roster: every row is then fixed, and this page writes none of them. */
export const ownedByTheClass = (personas: readonly Persona[]): boolean => personas.some((one) => one.fixed === true);

/** A persona the judge model wrote, kept as a file the class reads (`test/personas/<name>.json`) through the `pinecall start` in the agent's directory. */
export async function keepPersonaFile(credentials: Credentials, agent: string, persona: ProposedPersona): Promise<{ path: string; name: string }> {
  return (await dev(credentials, agent, "personas.write", persona)) as { path: string; name: string };
}

export type Written = PersonaPut;

const door = (agent: string, name?: string): string =>
  `/v1/agents/${encodeURIComponent(agent)}/personas${name === undefined ? "" : `/${encodeURIComponent(name)}`}`;

export async function readPersonas(credentials: Credentials, agent: string): Promise<Persona[]> {
  return PersonaListSchema.parse(await read(credentials, door(agent))).personas;
}

/** Every agent's callers, by agent and then by name. */
export async function readEveryPersona(credentials: Credentials): Promise<Persona[]> {
  return PersonaListSchema.parse(await read(credentials, "/v1/personas")).personas;
}

/** One page of the world's simulated calls to the agents named, newest first; `before` is the previous page's `next`. */
export async function readSimulations(credentials: Credentials, agents: readonly string[], before?: string): Promise<PersonaRunList> {
  const params = { agent: agents, ...(before === undefined ? {} : { before }) };
  return PersonaRunListSchema.parse(await read(credentials, "/v1/simulations", params));
}

/** One simulated call's row, by its id: who played the caller and what it cost; null for a call no persona made. */
export async function readSimulation(credentials: Credentials, call: string): Promise<PersonaRun | null> {
  return PersonaRunListSchema.parse(await read(credentials, "/v1/simulations", { call })).runs[0] ?? null;
}

/** Create, replace or rename a persona; resolves to the updated list. */
export async function writePersona(credentials: Credentials, agent: string, name: string, written: Written): Promise<Persona[]> {
  return PersonaListSchema.parse(await put(credentials, door(agent, name), written)).personas;
}

/** Switch one of Pinecall's personas on or off for the agent; resolves to the updated list. */
export async function switchPersona(credentials: Credentials, agent: string, name: string, on: boolean): Promise<Persona[]> {
  return PersonaListSchema.parse(await put(credentials, door(agent, name), { on })).personas;
}

/** How the agent plays one of Pinecall's personas: its model, voice vendor and voice, "" for the runtime's; resolves to the updated list. */
export async function playPersona(credentials: Credentials, agent: string, name: string, played: { llm: string; tts: string; voice: string }): Promise<Persona[]> {
  return PersonaListSchema.parse(await put(credentials, door(agent, name), played)).personas;
}

/** Callers written for the agent by the judge model, saved nowhere. */
export async function generatePersonas(
  credentials: Credentials,
  agent: string,
  asking: { about?: string; template?: string },
): Promise<GeneratedPersonas> {
  return GeneratedPersonasSchema.parse(await post(credentials, `${door(agent)}/generate`, asking));
}

/** Delete a persona; resolves to the updated list. */
export async function dropPersona(credentials: Credentials, agent: string, name: string): Promise<Persona[]> {
  return PersonaListSchema.parse(await drop(credentials, door(agent, name))).personas;
}

/** One page of a persona's simulations, newest first; `before` is the previous page's `next`. */
export async function readRuns(
  credentials: Credentials,
  agent: string,
  name: string,
  asked: { before?: string | undefined; limit?: number | undefined } = {},
): Promise<PersonaRunList> {
  const params = { ...(asked.before === undefined ? {} : { before: asked.before }), ...(asked.limit === undefined ? {} : { limit: asked.limit }) };
  return PersonaRunListSchema.parse(await read(credentials, `${door(agent, name)}/runs`, params));
}
