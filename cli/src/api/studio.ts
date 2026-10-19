/** The Studio endpoints: the org's agents built in the console — listed, made, read, saved, deployed, a tool tried, the code zipped. */

import { seg, type GatewayClient } from "./client.js";

// The Studio's shapes are the gateway's own and no SDK reads them: declared here, as the gateway answers them.

export type ParamType = "string" | "number" | "integer" | "boolean";

/** One header a request carries; its value may name `{{secrets.NAME}}`. */
export interface Header {
  name: string;
  value: string;
}

/** One argument the model fills: a path's `{name}`, else the query of a GET or the JSON body. */
export interface Param {
  name: string;
  type: ParamType;
  description: string;
  required: boolean;
}

/** A request to the business's own API the model may make, its answer what the model reads. */
export interface HttpTool {
  name: string;
  description: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url: string;
  headers: Header[];
  params: Param[];
  announce?: string | null;
  timeout_s: number;
}

/** One thing to collect from the caller. */
export interface CollectedField {
  name: string;
  type: ParamType;
  description: string;
  required: boolean;
}

/** Data collection: the fields the agent gathers, the call ended once the required ones are in. */
export interface Collect {
  fields: CollectedField[];
  end_when_done: boolean;
  closing: string;
  send_to?: string | null;
  headers: Header[];
}

/** How the agent opens a call: `say` the words, or `reply` to what the model reads first. */
export interface Greeting {
  say?: string | null;
  reply?: string | null;
}

/** A Studio agent: its instructions, how it opens, its tools, and what it collects. */
export interface Definition {
  instructions: string;
  greeting?: Greeting | null;
  tools: HttpTool[];
  collect?: Collect | null;
}

/** One Studio agent in one env: its newest release, its definition, who saved it, and when. */
export interface StudioAgent {
  name: string;
  env: "sandbox" | "production";
  release: number;
  definition: Definition;
  author: string;
  note: string;
  saved_at: number;
  stopped: boolean;
}

interface StudioAgentList {
  agents: StudioAgent[];
}

/** What one tool's request brought back: the status, the body as the model would read it, how long it took. */
export interface TryResult {
  status: number | null;
  body: unknown;
  error: string | null;
  duration_ms: number;
}

/** A part of a definition as a request sends it: what the gateway defaults may be left out. */
type Draft<T, Defaulted extends keyof T> = Omit<T, Defaulted> & { [K in Defaulted]?: T[K] | undefined };

export type ParamDraft = Draft<Param, "type" | "description" | "required">;
export type HttpToolDraft = Draft<Omit<HttpTool, "params">, "method" | "headers" | "announce" | "timeout_s"> & { params?: ParamDraft[] | undefined };
export type CollectDraft = Draft<Omit<Collect, "fields">, "end_when_done" | "closing" | "send_to" | "headers"> & { fields: Draft<CollectedField, "type" | "description" | "required">[] };

/** A definition as a request sends it. */
export interface DefinitionDraft {
  instructions: string;
  greeting?: Draft<Greeting, "say" | "reply"> | null | undefined;
  tools?: HttpToolDraft[] | undefined;
  collect?: CollectDraft | null | undefined;
}

// A note longer than this is cut: the gateway keeps it as a line, not a page.
const NOTE_LENGTH = 200;

function agentPath(name: string): string {
  return `/v1/studio/agents/${seg(name)}`;
}

export async function listAgents(gw: GatewayClient): Promise<StudioAgent[]> {
  return (await gw.get<StudioAgentList>("/v1/studio/agents")).agents;
}

/** `POST /v1/studio/agents`: the agent made, its first release the definition, or the gateway's template without one. */
export function createAgent(gw: GatewayClient, name: string, note: string, definition?: DefinitionDraft): Promise<StudioAgent> {
  return gw.post<StudioAgent>("/v1/studio/agents", { name, note: note.slice(0, NOTE_LENGTH), ...(definition === undefined ? {} : { definition }) });
}

export function getAgent(gw: GatewayClient, name: string): Promise<StudioAgent> {
  return gw.get<StudioAgent>(agentPath(name));
}

/** `PUT /v1/studio/agents/{name}`: the next release, over `based_on`; a 409 when someone saved meanwhile. */
export function saveAgent(gw: GatewayClient, name: string, definition: DefinitionDraft, basedOn: number | null, note: string): Promise<StudioAgent> {
  return gw.put<StudioAgent>(agentPath(name), { definition, based_on: basedOn, note: note.slice(0, NOTE_LENGTH) });
}

/** `POST /v1/studio/agents/{name}/deploy`, asked in the sandbox: its release, the newest unless named, as production's next. */
export function deployAgent(gw: GatewayClient, name: string, release: number | undefined, note: string): Promise<StudioAgent> {
  return gw.post<StudioAgent>(`${agentPath(name)}/deploy`, { note: note.slice(0, NOTE_LENGTH), ...(release === undefined ? {} : { release }) });
}

/** `POST /v1/studio/agents/{name}/try`: one tool's request sent once; over `definition` when it is not saved yet. */
export function tryTool(gw: GatewayClient, name: string, tool: string, args: Record<string, unknown>, definition?: DefinitionDraft): Promise<TryResult> {
  return gw.post<TryResult>(`${agentPath(name)}/try`, { tool, arguments: args, ...(definition === undefined ? {} : { definition }) });
}

/** `GET /v1/studio/agents/{name}/code`: the agent as a TypeScript project, the zip's bytes. */
export async function getCode(gw: GatewayClient, name: string): Promise<Uint8Array> {
  return new Uint8Array(await (await gw.fetch(`${agentPath(name)}/code`)).arrayBuffer());
}
