/** The server over real HTTP: the documents an assistant finds the sign-in by, the bearer asked for, and MCP spoken to a key the gateway takes. */

import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import { whoHolds } from "pinecall/hosted";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { Keys } from "../src/keys.js";
import { AUTHORIZATION_SERVER_PATH, listener, RESOURCE_PATHS, SCOPE } from "../src/server.js";
import { Sessions } from "../src/sessions.js";

const KEY = "pk_0123456789abcdef0123456789abcdef";
const WHO = { org: "org_1", slug: "clinica", key_id: "k_1", label: "Claude", env: "sandbox", name: "Ana", production: false };

let gateway: Server;
let front: Server;
let gatewayUrl: string;
let url: string;
const lines: string[] = [];

/** A server of the test's own on a free port, and its address. */
async function listening(server: Server): Promise<string> {
  await new Promise<void>((up) => server.listen(0, "127.0.0.1", up));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}

beforeAll(async () => {
  // The gateway, as far as these tests ask it: who a key is.
  gateway = createServer((request, response) => {
    const known = request.headers.authorization === `Bearer ${KEY}`;
    if (request.url !== "/v1/whoami") return void response.writeHead(404, { "content-type": "application/json" }).end(JSON.stringify({ detail: "Not Found" }));
    response.writeHead(known ? 200 : 401, { "content-type": "application/json" }).end(JSON.stringify(known ? WHO : { detail: "this key opens nothing here" }));
  });
  gatewayUrl = await listening(gateway);
  front = createServer();
  url = await listening(front);
  const settings = { port: 0, address: url, gateway: gatewayUrl };
  front.on("request", listener({ settings, keys: new Keys((key) => whoHolds(gatewayUrl, key)), sessions: new Sessions(gatewayUrl), log: (line) => void lines.push(line) }));
});

afterAll(async () => {
  for (const server of [front, gateway]) {
    server.closeAllConnections();
    await new Promise((closed) => server.close(closed));
  }
});

const spoken = (body: unknown, key?: string): Promise<Response> =>
  fetch(`${url}/mcp`, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", ...(key === undefined ? {} : { authorization: `Bearer ${key}` }) }, body: JSON.stringify(body) });

describe("before a sign-in", () => {
  it("says what it is and which gateway signs a person in, at both of RFC 9728's paths", async () => {
    for (const path of RESOURCE_PATHS) {
      const answer = await fetch(`${url}${path}`);
      expect(answer.headers.get("access-control-allow-origin")).toBe("*");
      expect(await answer.json()).toMatchObject({ resource: `${url}/mcp`, authorization_servers: [gatewayUrl], scopes_supported: [SCOPE], bearer_methods_supported: ["header"] });
    }
  });

  it("sends an assistant of the protocol's first revision on to the gateway's own document", async () => {
    const answer = await fetch(`${url}${AUTHORIZATION_SERVER_PATH}`, { redirect: "manual" });
    expect([answer.status, answer.headers.get("location")]).toEqual([307, `${gatewayUrl}${AUTHORIZATION_SERVER_PATH}`]);
  });

  it("asks for the sign-in with a challenge that names where to find it", async () => {
    const answer = await spoken({ jsonrpc: "2.0", id: 1, method: "tools/list" });
    expect(answer.status).toBe(401);
    expect(answer.headers.get("www-authenticate")).toBe(`Bearer resource_metadata="${url}${RESOURCE_PATHS[1]}", scope="${SCOPE}"`);
    expect(answer.headers.get("access-control-expose-headers")).toContain("WWW-Authenticate");
    expect(((await answer.json()) as { error: { message: string } }).error.message).toMatch(/connect Pinecall/);
    expect((await fetch(`${url}/mcp`)).status).toBe(401);
  });

  it("says a key the gateway does not take is no sign-in, and asks for another", async () => {
    const answer = await spoken({ jsonrpc: "2.0", id: 1, method: "tools/list" }, "pk_made_up");
    expect(answer.status).toBe(401);
    expect(answer.headers.get("www-authenticate")).toMatch(/^Bearer error="invalid_token", error_description="this sign-in opens nothing[^"]*", resource_metadata=/);
  });

  it("gives any page leave to ask, answers its health, and names its endpoint at any other path", async () => {
    const leave = await fetch(`${url}/mcp`, { method: "OPTIONS", headers: { origin: "https://claude.ai", "access-control-request-method": "POST", "access-control-request-headers": "authorization, content-type, mcp-protocol-version" } });
    expect([leave.status, leave.headers.get("access-control-allow-origin")]).toEqual([204, "*"]);
    expect(leave.headers.get("access-control-allow-headers")?.toLowerCase()).toContain("mcp-protocol-version");
    expect(await (await fetch(`${url}/health`)).json()).toEqual({ ok: true });
    expect(((await (await fetch(`${url}/`)).json()) as { mcp: string }).mcp).toBe(`${url}/mcp`);
    const lost = await fetch(`${url}/sse`, { method: "POST" });
    expect(lost.status).toBe(404);
    expect(((await lost.json()) as { error: { message: string } }).error.message).toContain(`${url}/mcp`);
  });
});

describe("with a key the gateway takes", () => {
  it("speaks MCP to a real client: the handshake, the hosted tools, a call on that key", async () => {
    const client = new Client({ name: "a-connector", version: "1" });
    // As in src/server.ts: the SDK's HTTP transports are Transports the compiler does not take for one.
    await client.connect(new StreamableHTTPClientTransport(new URL(`${url}/mcp`), { requestInit: { headers: { authorization: `Bearer ${KEY}` } } }) as Transport);
    expect(client.getServerVersion()?.name).toBe("pinecall");
    expect(client.getInstructions()).toContain("Pinecall's hosted server");
    const { tools } = await client.listTools();
    const names = tools.map((one) => one.name);
    expect(names).toEqual(expect.arrayContaining(["whoami", "agent", "calls", "chat", "docs_search"]));
    for (const machines of ["login", "project", "start", "runtime"]) expect(names).not.toContain(machines);
    for (const one of tools) expect(one._meta).toEqual({ securitySchemes: [{ type: "oauth2", scopes: [SCOPE] }] });
    const who = await client.callTool({ name: "whoami", arguments: {} });
    expect(who.isError).toBeFalsy();
    expect(JSON.parse((who.content as { text: string }[])[0]!.text)).toMatchObject({ org: "clinica", gateway: gatewayUrl, person: "Ana" });
    await client.close();
    expect(lines.some((line) => line.includes("whoami") && line.endsWith("ok"))).toBe(true);
    expect(lines.join("\n")).not.toContain(KEY);
  });

  it("opens no stream and keeps no session: a GET is told so, a body that is not JSON refused", async () => {
    const bearer = { authorization: `Bearer ${KEY}` };
    const stream = await fetch(`${url}/mcp`, { headers: { ...bearer, accept: "text/event-stream" } });
    expect([stream.status, stream.headers.get("allow")]).toEqual([405, "POST, OPTIONS"]);
    const broken = await fetch(`${url}/mcp`, { method: "POST", headers: { ...bearer, "content-type": "application/json" }, body: "{not json" });
    expect(broken.status).toBe(400);
  });
});
