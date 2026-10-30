/** An agent's simulated callers: Pinecall's switched on or off, its own written, generated, dropped, or the class's, pulled to files. */

import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { z } from "zod";

import * as api from "../../api/cases.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import * as providers from "../../providers/service.js";
import { AMBIENCES } from "./suite.js";

export type { Behavior, GeneratedPersonas, Persona, ProposedPersona } from "../../api/cases.js";

// Mirrors the gateway's name rule so a bad name gets a readable error.
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
// What a caller's numbers mean, in the refusal of one out of range.
const A_SHARE = (flag: string): string => `${flag} is a share of the agent's answers: a number from 0 to 1`;
const A_PAUSE = "--pause is seconds of silence before each line, 0 to 10";
const A_SPEED = "--speed is a multiple of the caller's usual pace, 0.5 to 2";

export const NOBODY = (name: string, agent: string): string => `no persona called ${name} for ${agent}: \`pinecall personas add ${name} --goal '…' --style '…'\`, or the console's Personas`;
export const PINECALLS = (name: string): string => `${name} is one of Pinecall's personas: \`pinecall personas on|off ${name}\` switches it; write your own under another name`;
export const SET_BY_THE_CLASS = (agent: string): string =>
  `personas set by the class of ${agent}: its callers are the files under agents/${agent}/test/personas/, and which of Pinecall's it plays is personas({ on }) in the class; nothing is written here`;

/** What `add` and `edit` take; on `edit` only the fields named change. */
export const WritePersonaInput = z.object({
  goal: z.string().min(1).optional(),
  style: z.string().min(1).optional(),
  about: z.string().optional(),
  facts: z.record(z.string(), z.string()).optional(),
  rename: z.string().optional(),
  llm: z.string().optional(),
  tts: z.string().optional(),
  voice: z.string().optional(),
  expects: z.array(z.string()).optional(),
  tags: z.array(z.string()).optional(),
  interrupts: z.number().min(0, A_SHARE("--interrupts")).max(1, A_SHARE("--interrupts")).optional(),
  pauseS: z.number().min(0, A_PAUSE).max(10, A_PAUSE).optional(),
  backchannels: z.number().min(0, A_SHARE("--backchannels")).max(1, A_SHARE("--backchannels")).optional(),
  speed: z.number().min(0.5, A_SPEED).max(2, A_SPEED).optional(),
  ambience: z.enum(AMBIENCES).optional(),
  backgroundNoise: z.number().nullable().optional(),
});
export type WritePersonaInput = z.infer<typeof WritePersonaInput>;

/** What `generate` takes: how many, a theme, a real call's caller, one of Pinecall's as the template, and whether to keep them. */
export const GenerateInput = z.object({
  n: z.number().int().min(1, "generate takes how many callers, 1 to 10").max(10, "generate takes how many callers, 1 to 10").default(3),
  about: z.string().optional(),
  fromCall: z.string().optional(),
  template: z.string().optional(),
  save: z.boolean().default(false),
});
export type GenerateInput = z.infer<typeof GenerateInput>;

/** Whether a persona of the list is the library's. */
export const isPinecalls = (persona: api.Persona): boolean => persona.owner === "pinecall";

/** Whether the agent's class owns its roster: every row of the list is then fixed, and no door writes one. */
export const ownedByTheClass = (listed: api.Persona[]): boolean => listed.some((one) => one.fixed === true);

/** The agent's callers: Pinecall's first, then its own. */
export async function listPersonas(ctx: Context, agent: string): Promise<api.Persona[]> {
  return api.listPersonas(ctx.gateway(), agent);
}

/** The agent's list, refused with where to write when its class owns it. */
async function writable(ctx: Context, agent: string): Promise<api.Persona[]> {
  const listed = await listPersonas(ctx, agent);
  if (ownedByTheClass(listed)) throw new UsageError(SET_BY_THE_CLASS(agent));
  return listed;
}

/** One persona by name; an unknown name is refused naming it. */
export async function getPersona(ctx: Context, agent: string, name: string): Promise<api.Persona> {
  const found = (await listPersonas(ctx, agent)).find((one) => one.name === name);
  if (found === undefined) throw new UsageError(NOBODY(name, agent));
  return found;
}

/** Write one of the agent's own, whole: on `add` new, on `edit` merged over what it is; the agent's list after. */
export async function writePersona(ctx: Context, agent: string, name: string, verb: "add" | "edit", input: WritePersonaInput): Promise<{ name: string; personas: api.Persona[] }> {
  const before = (await writable(ctx, agent)).find((one) => one.name === name);
  if (before !== undefined && isPinecalls(before)) throw new UsageError(PINECALLS(name));
  if (verb === "edit" && before === undefined) throw new UsageError(NOBODY(name, agent));
  if (verb === "add" && before !== undefined) throw new UsageError(`${agent} has a persona called ${name} already: \`pinecall personas edit ${name}\``);
  const writing = input.rename ?? name;
  if (!A_NAME.test(writing)) throw new UsageError(`${writing} is no name for a caller: lower-case letters and digits joined by hyphens — apurado, price-shopper`);
  const goal = input.goal ?? before?.goal;
  const style = input.style ?? before?.style;
  if (goal === undefined || style === undefined) throw new UsageError("a persona needs --goal and --style: what they want, and how they talk");
  // Unnamed fields keep their value; '' resets to the runtime default.
  const llm = input.llm === undefined || input.llm === "" ? input.llm : providers.modelFieldOf(input.llm);
  if (input.llm !== undefined && llm === undefined) throw new UsageError(providers.NOT_A_MODEL(input.llm));
  const personas = await api.putPersona(ctx.gateway(), agent, writing, {
    goal,
    style,
    about: input.about ?? before?.about ?? "",
    facts: input.facts ?? before?.facts ?? {},
    state: before?.state ?? {},
    llm: llm === "" ? null : (llm ?? before?.llm ?? null),
    tts: input.tts === "" ? null : (input.tts ?? before?.tts ?? null),
    voice: input.voice === "" ? null : (input.voice ?? before?.voice ?? null),
    expects: input.expects ?? before?.expects ?? [],
    tags: input.tags ?? before?.tags ?? [],
    behavior: {
      ...(before?.behavior ?? {}),
      ...(input.interrupts === undefined ? {} : { interrupts: input.interrupts }),
      ...(input.pauseS === undefined ? {} : { pause_s: input.pauseS }),
      ...(input.backchannels === undefined ? {} : { backchannels: input.backchannels }),
      ...(input.speed === undefined ? {} : { speed: input.speed }),
      ...(input.ambience === undefined ? {} : { ambience: input.ambience }),
      ...(input.backgroundNoise === undefined ? {} : { interferer_db: input.backgroundNoise }),
    },
    ...(writing === name ? {} : { was: name }),
  });
  return { name: writing, personas };
}

/** One of the agent's own dropped; one of Pinecall's is switched off instead. */
export async function dropPersona(ctx: Context, agent: string, name: string): Promise<{ name: string; personas: api.Persona[] }> {
  const found = (await writable(ctx, agent)).find((one) => one.name === name);
  if (found === undefined) throw new UsageError(NOBODY(name, agent));
  if (isPinecalls(found)) throw new UsageError(`${name} is one of Pinecall's personas and is never dropped: \`pinecall personas off ${name}\``);
  return { name, personas: await api.deletePersona(ctx.gateway(), agent, name) };
}

/** One of Pinecall's switched for the agent: the nightly plays what is on. */
export async function switchPersona(ctx: Context, agent: string, name: string, on: boolean): Promise<{ name: string; on: boolean; personas: api.Persona[] }> {
  const found = (await writable(ctx, agent)).find((one) => one.name === name);
  if (found === undefined || !isPinecalls(found)) throw new UsageError(`${name} is not one of Pinecall's personas: \`pinecall personas\` lists them; your own play while written`);
  return { name, on, personas: await api.putPersona(ctx.gateway(), agent, name, { on }) };
}

/** What `generate --save` did with the callers: rows written, or files under the folder the class reads. */
export interface Saved {
  saved: boolean;
  /** The files written, when the class owns the roster; empty when rows were written or nothing was kept. */
  files: string[];
}

/**
 * Callers written by the judge model from the agent; kept with `save`: as the agent's rows, or, when the
 * class owns its roster, as files under `folder` (`agents/<agent>/test/personas/`), which the class reads.
 */
export async function generatePersonas(ctx: Context, agent: string, input: GenerateInput, folder?: string): Promise<api.GeneratedPersonas & Saved> {
  const gw = ctx.gateway();
  const written = await api.generatePersonas(gw, agent, {
    n: input.n,
    ...(input.about === undefined ? {} : { about: input.about }),
    ...(input.fromCall === undefined ? {} : { from_call: input.fromCall }),
    ...(input.template === undefined ? {} : { template: input.template }),
  });
  if (!input.save) return { ...written, saved: false, files: [] };
  if (folder !== undefined && ownedByTheClass(await listPersonas(ctx, agent))) {
    const files: string[] = [];
    for (const persona of written.personas) files.push(await writePersonaFile(folder, persona));
    return { ...written, saved: true, files };
  }
  for (const persona of written.personas) {
    const { name, ...rest } = persona;
    await api.putPersona(gw, agent, name, rest);
  }
  return { ...written, saved: true, files: [] };
}

/** A persona as its file holds it: what `PUT …/personas/{name}` takes, the name being the file's. */
export type PersonaFile = Omit<api.PersonaWrite, "was" | "on">;

/** One caller written as `<folder>/<name>.json`, what the class reads; the same name again is replaced. */
export async function writePersonaFile(folder: string, persona: { name: string } & PersonaFile): Promise<string> {
  const { name, ...rest } = persona;
  if (!A_NAME.test(name)) throw new UsageError(`${name} is no name for a caller: lower-case letters and digits joined by hyphens — apurado, price-shopper`);
  await mkdir(folder, { recursive: true });
  const path = join(folder, `${name}.json`);
  await writeFile(path, `${JSON.stringify(rest, null, 2)}\n`, "utf8");
  return path;
}

/**
 * The agent's own callers the gateway keeps, written once as files under `folder` for a class that is
 * about to declare them; the rows stay, and `pinecall personas rm` drops them once the class owns the roster.
 */
export async function pullPersonas(ctx: Context, agent: string, folder: string): Promise<{ files: string[] }> {
  const own = (await listPersonas(ctx, agent)).filter((one) => !isPinecalls(one) && one.owner !== "class");
  const files: string[] = [];
  for (const one of own) {
    const { name, about, goal, style, facts, state, llm, tts, voice, expects, tags, behavior } = one;
    files.push(await writePersonaFile(folder, { name, about, goal, style, facts, state, llm, tts, voice, expects, tags, behavior }));
  }
  return { files };
}

/** Repeated `--fact 'what=said'` flags as a map. */
export function factsOf(said: string[]): Record<string, string> {
  const facts: Record<string, string> = {};
  for (const one of said) {
    const at = one.indexOf("=");
    if (at <= 0) throw new UsageError("a fact is what=said: --fact 'their phone=305 555 0101'");
    facts[one.slice(0, at).trim()] = one.slice(at + 1).trim();
  }
  return facts;
}
