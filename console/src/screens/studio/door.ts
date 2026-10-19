/** Studio's doors: an agent built in the console — read, made, saved, deployed, one tool tried, and its code downloaded. */

import { z } from "zod";

import { answered, doorUrl, headersFor, post, put, read, type Credentials } from "@pinecall/core/api";

// runtime studio/schemas.py, field for field.
const ParamTypeSchema = z.enum(["string", "number", "integer", "boolean"]);
const HeaderSchema = z.object({ name: z.string(), value: z.string() });
const ParamSchema = z.object({ name: z.string(), type: ParamTypeSchema, description: z.string(), required: z.boolean() });

const HttpToolSchema = z.object({
  name: z.string(),
  description: z.string(),
  method: z.enum(["GET", "POST", "PUT", "PATCH", "DELETE"]),
  url: z.string(),
  headers: z.array(HeaderSchema),
  params: z.array(ParamSchema),
  announce: z.string().nullable().optional(),
  timeout_s: z.number(),
});

const CollectSchema = z.object({
  fields: z.array(ParamSchema),
  end_when_done: z.boolean(),
  closing: z.string(),
  send_to: z.string().nullable().optional(),
  headers: z.array(HeaderSchema),
});

const GreetingSchema = z.object({ say: z.string().nullable().optional(), reply: z.string().nullable().optional() });

const DefinitionSchema = z.object({
  instructions: z.string(),
  greeting: GreetingSchema.nullable().optional(),
  tools: z.array(HttpToolSchema),
  collect: CollectSchema.nullable().optional(),
});

const StudioAgentSchema = z.object({
  name: z.string(),
  env: z.enum(["sandbox", "production"]),
  release: z.number().int(),
  definition: DefinitionSchema,
  author: z.string(),
  note: z.string(),
  saved_at: z.number(),
  stopped: z.boolean(),
});

const TriedSchema = z.object({ status: z.number().int().nullable(), body: z.unknown(), error: z.string().nullable(), duration_ms: z.number() });

export type ParamType = z.infer<typeof ParamTypeSchema>;
export type Header = z.infer<typeof HeaderSchema>;
/** A tool's parameter, and a field data collection gathers: the same four things. */
export type Param = z.infer<typeof ParamSchema>;
export type Method = z.infer<typeof HttpToolSchema>["method"];
export type HttpTool = z.infer<typeof HttpToolSchema>;
export type Collect = z.infer<typeof CollectSchema>;
export type Greeting = z.infer<typeof GreetingSchema>;
export type Definition = z.infer<typeof DefinitionSchema>;
/** One Studio agent in one world: its newest release and what it is. */
export type StudioAgent = z.infer<typeof StudioAgentSchema>;
/** What one tool's request answered when it was tried. */
export type Tried = z.infer<typeof TriedSchema>;

const doorOf = (name: string): string => `/v1/studio/agents/${encodeURIComponent(name)}`;

/** The agent's newest release in this world. */
export async function readStudioAgent(credentials: Credentials, name: string): Promise<StudioAgent> {
  return StudioAgentSchema.parse(await read(credentials, doorOf(name)));
}

/** A new agent in the sandbox, by its name alone: it starts with the gateway's first instructions. */
export async function makeStudioAgent(credentials: Credentials, name: string): Promise<StudioAgent> {
  return StudioAgentSchema.parse(await post(credentials, "/v1/studio/agents", { name }));
}

/** The definition kept as the next release, over the release it was read at. */
export async function saveStudioAgent(credentials: Credentials, name: string, definition: Definition, basedOn: number): Promise<StudioAgent> {
  return StudioAgentSchema.parse(await put(credentials, doorOf(name), { definition, based_on: basedOn }));
}

/** The sandbox's release copied into production, with the sandbox's credentials; answers production's. */
export async function deployStudioAgent(credentials: Credentials, name: string, release: number): Promise<StudioAgent> {
  return StudioAgentSchema.parse(await post(credentials, `${doorOf(name)}/deploy`, { release }));
}

/** One tool's request sent once, with the definition as the editor holds it. */
export async function tryTool(credentials: Credentials, name: string, tool: string, args: Record<string, unknown>, definition: Definition): Promise<Tried> {
  return TriedSchema.parse(await post(credentials, `${doorOf(name)}/try`, { tool, arguments: args, definition }));
}

// A download needs the key in a header, which a plain link cannot carry: the zip is fetched with
// the key and handed to the browser as a file.
/** The agent exported as a TypeScript project, as a zip. */
export async function readCode(credentials: Credentials, name: string): Promise<Blob> {
  const answer = await fetch(doorUrl(credentials, `${doorOf(name)}/code`), { headers: headersFor(credentials) });
  if (!answer.ok) await answered(answer);
  return answer.blob();
}
