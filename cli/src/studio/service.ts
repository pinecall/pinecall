/** Studio: the org's agents built in the console — listed, made, pulled to a file and pushed over the release read, a tool tried, deployed, their code downloaded. */

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

import { z } from "zod";

import * as api from "../api/studio.js";
import type { Context } from "../context.js";
import { GatewayError, UsageError } from "../errors.js";
import { readJsonFile } from "../kit/json-file.js";
import { unzip } from "../kit/zip.js";

export type { Definition, StudioAgent, TryResult } from "../api/studio.js";

const PARAM_TYPE = z.enum(["string", "number", "integer", "boolean"]);

const HeaderInput = z.strictObject({
  name: z.string(),
  value: z.string().describe("the header's value; `{{secrets.NAME}}` names a secret of the org's, set with `pinecall secrets set` — never the secret itself"),
});

const ParamInput = z.strictObject({
  name: z.string().describe("letters, digits and underscores"),
  type: PARAM_TYPE.optional().describe("string when left out"),
  description: z.string().optional().describe("what the model fills it with"),
  required: z.boolean().optional().describe("true when left out"),
});

const HttpToolInput = z.strictObject({
  name: z.string().describe("the tool's name: letters, digits and underscores"),
  description: z.string().describe("what it does, so the model knows when to call it"),
  method: z.enum(["GET", "POST", "PUT", "PATCH", "DELETE"]).optional().describe("GET when left out"),
  url: z.string().describe("the request's https URL; a param named in it as `{name}` fills the path"),
  headers: z.array(HeaderInput).optional(),
  params: z.array(ParamInput).optional().describe("the arguments the model fills: a path's `{name}`, else the query of a GET or the JSON body"),
  announce: z.string().nullable().optional().describe("what the agent says while the request runs"),
  timeout_s: z.number().optional().describe("how long the request may take, in seconds; 10 when left out, 30 at most"),
});

const CollectInput = z.strictObject({
  fields: z.array(ParamInput).describe("what the agent gathers from the caller, each with its name, type and what it is"),
  end_when_done: z.boolean().optional().describe("the call ends once every required field is in; true when left out"),
  closing: z.string().optional().describe("what the agent does once every required field is in, as an instruction to the model"),
  send_to: z.string().nullable().optional().describe("a URL the fields are posted to when the call ends, with the transcript"),
  headers: z.array(HeaderInput).optional().describe("the headers that post carries"),
});

const GreetingInput = z.strictObject({
  say: z.string().nullable().optional().describe("the words the agent opens with"),
  reply: z.string().nullable().optional().describe("what the model reads first and answers, for an opening of its own"),
});

/** A whole definition, as `pinecall studio push` and the MCP's `save` send it; the gateway checks the rest and fills what is left out. */
export const DefinitionInput = z.strictObject({
  instructions: z.string().min(1).describe("the agent's instructions: who it is, what it does, how it speaks"),
  greeting: GreetingInput.nullable().optional().describe("how it opens a call: `say` or `reply`, one of the two; the caller speaks first when null"),
  tools: z.array(HttpToolInput).optional().describe("the HTTP requests the model may make, each answer what it reads"),
  collect: CollectInput.nullable().optional().describe("data collection: the fields gathered, and where they go when the call ends"),
});
export type DefinitionInput = z.infer<typeof DefinitionInput>;

/** The file `pull` writes and `push` reads: the release it was read at, beside the definition. */
export const StudioFile = z.strictObject({ release: z.number().int().min(1), definition: DefinitionInput });
export type StudioFile = z.infer<typeof StudioFile>;

/** Where `pull` writes and `push` reads unless told. */
export const STUDIO_FILE = (name: string): string => `${name}.studio.json`;
export const NOT_A_PAIR = (word: string): string => `${word} is not key=value: one argument of the tool, as its params name it`;
export const NOT_A_STUDIO_FILE = (file: string, why: string): string => `${file} is not what \`pinecall studio pull\` writes: ${why}`;
export const ALREADY_THERE = (path: string): string => `${path} is there already: the code is written into a folder that does not hold it yet — choose another --out`;

// A number as JSON writes one: a phone number's `+` or a leading zero keeps the word text.
const A_NUMBER = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;

/** A definition written to a file, and the release it was read at. */
export interface Pulled {
  name: string;
  release: number;
  file: string;
}

/** A file saved as the next release; `release` is `based_on` again when nothing in it changed. */
export interface Pushed {
  agent: api.StudioAgent;
  basedOn: number;
  file: string;
}

/** The agent's code: the zip saved (`file`), or its files written into a folder (`folder`). */
export interface Code {
  name: string;
  file: string | null;
  folder: string | null;
  bytes: number;
  files: number;
}

export async function listAgents(ctx: Context): Promise<api.StudioAgent[]> {
  return api.listAgents(ctx.gateway());
}

export async function getAgent(ctx: Context, name: string): Promise<api.StudioAgent> {
  return api.getAgent(ctx.gateway(), name);
}

/** The agent made; without a definition it starts from the gateway's template. */
export async function createAgent(ctx: Context, name: string, note: string, definition?: DefinitionInput): Promise<api.StudioAgent> {
  return api.createAgent(ctx.gateway(), name, note, definition);
}

/** The definition kept as the next release, over `basedOn`: the gateway refuses it (409) when someone saved meanwhile. */
export async function saveAgent(ctx: Context, name: string, definition: DefinitionInput, basedOn: number | null, note: string): Promise<api.StudioAgent> {
  return api.saveAgent(ctx.gateway(), name, definition, basedOn, note);
}

/** The newest release written to a file as `{release, definition}`: what a push saves over. */
export async function pullAgent(ctx: Context, name: string, out?: string): Promise<Pulled> {
  const agent = await api.getAgent(ctx.gateway(), name);
  const file = out ?? STUDIO_FILE(name);
  writeStudioFile(resolve(ctx.cwd, file), { release: agent.release, definition: agent.definition });
  return { name, release: agent.release, file };
}

/**
 * The file saved as the next release, based on the release it was pulled at; a 409 says someone
 * saved meanwhile and the file is pulled again. Saved, the file stands at the new release, so the
 * next push goes over it.
 */
export async function pushAgent(ctx: Context, name: string, file: string | undefined, note: string): Promise<Pushed> {
  const typed = file ?? STUDIO_FILE(name);
  const path = resolve(ctx.cwd, typed);
  const read = StudioFile.safeParse(readJsonFile("--file", path));
  if (!read.success) throw new UsageError(NOT_A_STUDIO_FILE(typed, read.error.issues.map((issue) => `${issue.path.join(".") || "the file"}: ${issue.message}`).join("; ")));
  let agent: api.StudioAgent;
  try {
    agent = await api.saveAgent(ctx.gateway(), name, read.data.definition, read.data.release, note);
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === 409) throw new GatewayError(409, `${failed.detail} — \`pinecall studio pull ${name}\` writes it again`);
    throw failed;
  }
  writeStudioFile(path, { release: agent.release, definition: read.data.definition });
  return { agent, basedOn: read.data.release, file: typed };
}

/** `key=value` words as a tool's arguments: a number or true/false read as one, anything else text. */
export function toolArguments(words: readonly string[]): Record<string, unknown> {
  const args: Record<string, unknown> = {};
  for (const word of words) {
    const at = word.indexOf("=");
    if (at <= 0) throw new UsageError(NOT_A_PAIR(word));
    const text = word.slice(at + 1);
    args[word.slice(0, at)] = text === "true" ? true : text === "false" ? false : A_NUMBER.test(text) ? Number(text) : text;
  }
  return args;
}

/** One tool's request sent once, as a call would send it; over `definition` when it is not saved yet. */
export async function tryTool(ctx: Context, name: string, tool: string, args: Record<string, unknown>, definition?: DefinitionInput): Promise<api.TryResult> {
  return api.tryTool(ctx.gateway(), name, tool, args, definition);
}

/** The sandbox's release, its newest unless named, kept as production's next; asked in the sandbox. */
export async function deployAgent(ctx: Context, name: string, release: number | undefined, note: string): Promise<api.StudioAgent> {
  if (release !== undefined && (!Number.isInteger(release) || release < 1)) throw new UsageError(`--release ${release}: a release is its number, from \`pinecall studio list\``);
  return api.deployAgent(ctx.gateway(), name, release, note);
}

/** The agent as a TypeScript project: the zip saved as `<name>.zip`, or with `out` its files written there. */
export async function downloadCode(ctx: Context, name: string, out?: string): Promise<Code> {
  const zipped = await api.getCode(ctx.gateway(), name);
  if (out === undefined) {
    const file = `${name}.zip`;
    writeFileSync(join(ctx.cwd, file), zipped);
    return { name, file, folder: null, bytes: zipped.length, files: 0 };
  }
  const root = resolve(ctx.cwd, out);
  const entries = unzip(zipped);
  const there = entries.find((entry) => existsSync(join(root, entry.path)));
  if (there !== undefined) throw new UsageError(ALREADY_THERE(join(out, there.path)));
  for (const entry of entries) {
    const path = join(root, entry.path);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, entry.data);
  }
  // The gateway packs the project under a folder of the agent's name.
  const nested = entries.length > 0 && entries.every((entry) => entry.path.startsWith(`${name}/`));
  return { name, file: null, folder: nested ? join(out, name) : out, bytes: zipped.length, files: entries.length };
}

function writeStudioFile(path: string, file: { release: number; definition: unknown }): void {
  writeFileSync(path, `${JSON.stringify(file, null, 2)}\n`);
}
