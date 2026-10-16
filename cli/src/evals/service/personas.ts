/** An agent's simulated callers: Pinecall's switched on or off, its own written, generated, dropped, and the file-kept ones pushed once. */

import { readdir, stat } from "node:fs/promises";
import { basename, extname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { z } from "zod";

import * as api from "../../api/cases.js";
import type { Context } from "../../context.js";
import { PinecallError, UsageError, errorMessage } from "../../errors.js";
import * as providers from "../../providers/service.js";
import { AMBIENCES } from "./suite.js";

export type { Behavior, GeneratedPersonas, Persona, ProposedPersona } from "../../api/cases.js";

// Mirrors the gateway's name rule so a bad name gets a readable error.
const A_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const NOBODY = (name: string, agent: string): string => `no persona called ${name} for ${agent}: \`pinecall personas add ${name} --goal '…' --style '…'\`, or the console's Personas`;
export const PINECALLS = (name: string): string => `${name} is one of Pinecall's personas: \`pinecall personas on|off ${name}\` switches it; write your own under another name`;

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
  interrupts: z.number().min(0).max(1).optional(),
  pauseS: z.number().min(0).max(10).optional(),
  backchannels: z.number().min(0).max(1).optional(),
  speed: z.number().min(0.5).max(2).optional(),
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

/** The agent's callers: Pinecall's first, then its own. */
export async function listPersonas(ctx: Context, agent: string): Promise<api.Persona[]> {
  return api.listPersonas(ctx.gateway(), agent);
}

/** One persona by name; an unknown name is refused naming it. */
export async function getPersona(ctx: Context, agent: string, name: string): Promise<api.Persona> {
  const found = (await listPersonas(ctx, agent)).find((one) => one.name === name);
  if (found === undefined) throw new UsageError(NOBODY(name, agent));
  return found;
}

/** Write one of the agent's own, whole: on `add` new, on `edit` merged over what it is; the agent's list after. */
export async function writePersona(ctx: Context, agent: string, name: string, verb: "add" | "edit", input: WritePersonaInput): Promise<{ name: string; personas: api.Persona[] }> {
  const before = (await listPersonas(ctx, agent)).find((one) => one.name === name);
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
  const found = await getPersona(ctx, agent, name);
  if (isPinecalls(found)) throw new UsageError(`${name} is one of Pinecall's personas and is never dropped: \`pinecall personas off ${name}\``);
  return { name, personas: await api.deletePersona(ctx.gateway(), agent, name) };
}

/** One of Pinecall's switched for the agent: the nightly plays what is on. */
export async function switchPersona(ctx: Context, agent: string, name: string, on: boolean): Promise<{ name: string; on: boolean; personas: api.Persona[] }> {
  const found = (await listPersonas(ctx, agent)).find((one) => one.name === name);
  if (found === undefined || !isPinecalls(found)) throw new UsageError(`${name} is not one of Pinecall's personas: \`pinecall personas\` lists them; your own play while written`);
  return { name, on, personas: await api.putPersona(ctx.gateway(), agent, name, { on }) };
}

/** Callers written by the judge model from the agent; kept as its own with `save`. */
export async function generatePersonas(ctx: Context, agent: string, input: GenerateInput): Promise<api.GeneratedPersonas & { saved: boolean }> {
  const gw = ctx.gateway();
  const written = await api.generatePersonas(gw, agent, {
    n: input.n,
    ...(input.about === undefined ? {} : { about: input.about }),
    ...(input.fromCall === undefined ? {} : { from_call: input.fromCall }),
    ...(input.template === undefined ? {} : { template: input.template }),
  });
  if (input.save) {
    for (const persona of written.personas) {
      const { name, ...rest } = persona;
      await api.putPersona(gw, agent, name, rest);
    }
  }
  return { ...written, saved: input.save };
}

/**
 * The personas still in files (`agents/<agent>/test/personas/*.ts`, each default-exporting one) sent to the
 * gateway once, as that agent's: the migration. A refusal names what landed and what is left.
 */
/**
 * The personas written under the agent's `test/personas/` that the gateway does not list: for a
 * list that says what `personas push` would send. None outside a project, or for a bare slug.
 */
export async function personasNotPushed(ctx: Context, choice: { agent?: string | undefined; file?: string | undefined }, listed: api.Persona[]): Promise<string[]> {
  let folder: string;
  try {
    folder = ctx.agent("personas", choice).personas;
  } catch {
    return [];
  }
  const names = new Set(listed.map((one) => one.name));
  return (await personasInFiles(folder)).map((one) => one.name).filter((name) => !names.has(name));
}

export async function pushPersonaFiles(ctx: Context, agent: string, folder: string): Promise<{ pushed: string[]; personas: api.Persona[] }> {
  const inFiles = await personasInFiles(folder);
  if (inFiles.length === 0) throw new UsageError(`no personas in ${folder}`);
  const pushed: string[] = [];
  let personas: api.Persona[] = [];
  for (const persona of inFiles) {
    try {
      personas = await api.putPersona(ctx.gateway(), agent, persona.name, {
        goal: persona.goal,
        style: persona.style,
        about: "",
        facts: Object.fromEntries(Object.entries(persona.facts ?? {}).map(([what, said]) => [what, String(said)])),
        state: persona.state ?? {},
      });
    } catch (refused) {
      const left = inFiles.map((one) => one.name).slice(pushed.length);
      throw new PinecallError(
        [
          `${left[0]} was refused: ${errorMessage(refused)}`,
          `  pushed: ${pushed.length === 0 ? "nothing" : pushed.join(", ")}`,
          `  still only files: ${left.join(", ")}`,
          "  nothing was undone and no file was touched: push again once it is fixed",
        ].join("\n"),
      );
    }
    pushed.push(persona.name);
  }
  return { pushed, personas };
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

/** A persona file as it was written before the gateway kept them. */
interface FilePersona {
  name: string;
  goal: string;
  style: string;
  facts?: Record<string, unknown>;
  state?: Record<string, unknown>;
}

// The files are TypeScript a project never builds; tsx is loaded only here.
async function personasInFiles(folder: string): Promise<FilePersona[]> {
  const names = await readdir(resolve(folder)).catch(() => []);
  const files = names.filter((name) => extname(name) === ".ts").sort();
  if (files.length === 0) return [];
  const { register } = await import("tsx/esm/api");
  const unregister = register();
  try {
    return await Promise.all(
      files.map(async (name) => {
        const file = join(resolve(folder), name);
        // Cache-bust by mtime so an edited file is re-imported.
        const loaded = (await import(`${pathToFileURL(file).href}?v=${(await stat(file)).mtimeMs}`)) as { default?: unknown };
        if (typeof loaded.default !== "object" || loaded.default === null) throw new UsageError(`${file} has no default-exported persona`);
        return { ...(loaded.default as FilePersona), name: basename(file, extname(file)) };
      }),
    );
  } finally {
    await unregister();
  }
}
