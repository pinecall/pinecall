/** The HTTP the server speaks: MCP's Streamable HTTP at one path behind a bearer, and the documents an assistant finds the sign-in by. */

import type { IncomingMessage, ServerResponse } from "node:http";

import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import { hostedServer, version, type Trace } from "pinecall/hosted";

import type { Keys } from "./keys.js";
import type { Sessions } from "./sessions.js";
import { MCP_PATH, type Settings } from "./settings.js";

/** The one word a connection asks for: whatever the person's own key opens. */
export const SCOPE = "pinecall";
/** RFC 9728's document, at the root and at the path of the endpoint: an assistant asks either. */
export const RESOURCE_PATHS = ["/.well-known/oauth-protected-resource", `/.well-known/oauth-protected-resource${MCP_PATH}`];
/** Where an assistant written to the protocol's first revision looks for the sign-in: sent on to the gateway, which holds it. */
export const AUTHORIZATION_SERVER_PATH = "/.well-known/oauth-authorization-server";
export const DOCS = "https://docs.pinecall.io/mcp/connect/";
// A tool's arguments are a definition or a document at most; the gateway's own ceiling is larger.
export const LARGEST_BODY = 4 * 1024 * 1024;

// Read by any page: a bearer is never ambient, so no origin holds anything of anybody's here.
const ANY_PAGE = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Mcp-Session-Id, Mcp-Protocol-Version, Last-Event-ID",
  "Access-Control-Expose-Headers": "Mcp-Session-Id, WWW-Authenticate",
  "Access-Control-Max-Age": "600",
};
// JSON-RPC's own codes, and the one the SDK's servers answer a request with no session or sign-in by.
const PARSE_ERROR = -32700;
const REFUSED = -32001;

/** What a host is told of every tool: it is opened by the sign-in (ChatGPT reads it to offer the connection). */
const TOOL_META = { securitySchemes: [{ type: "oauth2", scopes: [SCOPE] }] };

export interface Front {
  settings: Settings;
  keys: Keys;
  sessions: Sessions;
  /** One line per request and per tool call: never a key, an argument or an answer. */
  log: Trace;
}

/** The listener of the server: every request answered, none thrown out of it. */
export function listener(front: Front): (request: IncomingMessage, response: ServerResponse) => void {
  return (request, response) => {
    const started = Date.now();
    const path = new URL(request.url ?? "/", front.settings.address).pathname;
    response.on("finish", () => front.log(`pinecall-mcp · ${request.method} ${path} · ${response.statusCode} · ${Date.now() - started} ms`));
    void answer(front, request, response, path).catch((failed: unknown) => {
      front.log(`pinecall-mcp · ${request.method} ${path} · failed: ${failed instanceof Error ? failed.message : String(failed)}`);
      if (!response.headersSent) refuse(response, 500, "the server failed to answer this request");
      else response.end();
    });
  };
}

async function answer(front: Front, request: IncomingMessage, response: ServerResponse, path: string): Promise<void> {
  const { settings } = front;
  if (request.method === "OPTIONS") return void response.writeHead(204, ANY_PAGE).end();
  if (path === "/health") return json(response, 200, { ok: true });
  if (path === "/") return json(response, 200, { name: "pinecall-mcp", version: version(), mcp: `${settings.address}${MCP_PATH}`, docs: DOCS });
  if (RESOURCE_PATHS.includes(path)) return json(response, 200, resourceOf(settings));
  if (path === AUTHORIZATION_SERVER_PATH) return void response.writeHead(307, { ...ANY_PAGE, Location: `${settings.gateway}${AUTHORIZATION_SERVER_PATH}` }).end();
  if (path !== MCP_PATH) return refuse(response, 404, `nothing at ${path}: the MCP endpoint is ${settings.address}${MCP_PATH}`);

  const key = bearerOf(request);
  if (key === null) return unauthorized(response, settings);
  let opens: boolean;
  try {
    opens = await front.keys.opens(key);
  } catch {
    return refuse(response, 503, "Pinecall could not be asked who this key is: try again");
  }
  if (!opens) return unauthorized(response, settings, "this sign-in opens nothing: it was ended, it expired, or it never existed. Connect Pinecall again");
  // Stateless: each request is whole, so there is no stream to open and no session to end.
  if (request.method !== "POST") return void response.writeHead(405, { ...ANY_PAGE, Allow: "POST, OPTIONS" }).end();

  let body: unknown;
  try {
    body = JSON.parse(await read(request));
  } catch (failed) {
    return refuse(response, failed instanceof TooLarge ? 413 : 400, failed instanceof TooLarge ? failed.message : "the body is not JSON", PARSE_ERROR);
  }
  const server = hostedServer(front.sessions.of(key), { trace: front.log, meta: TOOL_META });
  // No session id is made: each request is whole.
  const transport = new StreamableHTTPServerTransport({ enableJsonResponse: true });
  response.on("close", () => {
    void transport.close();
    void server.close();
  });
  for (const [name, value] of Object.entries(ANY_PAGE)) response.setHeader(name, value);
  // The SDK's HTTP transport keeps `onclose` behind an accessor, which is no optional property under
  // exactOptionalPropertyTypes: it is a Transport all the same (@modelcontextprotocol/sdk 1.32.1).
  await server.connect(transport as Transport);
  await transport.handleRequest(request, response, body);
}

/** RFC 9728: what this server is, and the gateway a person signs in at to use it. */
export function resourceOf(settings: Settings): Record<string, unknown> {
  return {
    resource: `${settings.address}${MCP_PATH}`,
    authorization_servers: [settings.gateway],
    scopes_supported: [SCOPE],
    bearer_methods_supported: ["header"],
    resource_name: "Pinecall",
    resource_documentation: DOCS,
  };
}

/** RFC 6750 and RFC 9728: the challenge an assistant reads to start the sign-in, or to start it again. */
export function challengeOf(settings: Settings, why?: string): string {
  const said = [`resource_metadata="${settings.address}${RESOURCE_PATHS[1]}"`, `scope="${SCOPE}"`];
  if (why !== undefined) said.unshift('error="invalid_token"', `error_description="${why.replaceAll('"', "'")}"`);
  return `Bearer ${said.join(", ")}`;
}

function unauthorized(response: ServerResponse, settings: Settings, why?: string): void {
  response.setHeader("WWW-Authenticate", challengeOf(settings, why));
  refuse(response, 401, why ?? "connect Pinecall to use this server: it takes a sign-in");
}

function bearerOf(request: IncomingMessage): string | null {
  const [scheme, key] = (request.headers.authorization ?? "").split(" ");
  return scheme?.toLowerCase() === "bearer" && key !== undefined && key !== "" ? key : null;
}

class TooLarge extends Error {}

async function read(request: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request as AsyncIterable<Buffer>) {
    size += chunk.length;
    if (size > LARGEST_BODY) throw new TooLarge(`the body is over ${LARGEST_BODY / (1024 * 1024)} MiB`);
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

function json(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, { ...ANY_PAGE, "Content-Type": "application/json", "Cache-Control": "no-store" }).end(JSON.stringify(body));
}

// A refusal as the protocol says one, so an assistant shows its sentence whatever the status.
function refuse(response: ServerResponse, status: number, message: string, code = REFUSED): void {
  json(response, status, { jsonrpc: "2.0", error: { code, message }, id: null });
}
