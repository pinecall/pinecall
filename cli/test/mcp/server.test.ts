/** The MCP server end to end over an in-memory transport: every tool listed with its manual, a call answered scrubbed, a refusal one sentence. */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { afterEach, describe, expect, it } from "vitest";

import { createServer } from "../../src/mcp/server.js";
import { Session } from "../../src/mcp/session.js";
import { TOOLS } from "../../src/mcp/tools/index.js";
import { answer, GATEWAY, KEY, refuse } from "../support/gateway.js";
import { folder, project } from "../support/project.js";

const WHO = { org: "org_1", slug: "clinica", key_id: "k_1", label: null, env: "sandbox", name: `Ana, whose key is ${KEY}`, production: false };

let client: Client | undefined;

afterEach(async () => {
  await client?.close();
  client = undefined;
});

/** A host connected to a server whose session works in `root`, the key in its environment. */
async function connected(root: string | undefined): Promise<Client> {
  const processEnv = { PINECALL_KEY: KEY, PINECALL_URL: GATEWAY, PINECALL_HOME: folder() };
  const session = new Session(processEnv, async () => (root === undefined ? [] : [root]));
  const server = createServer("0.0.0-test", processEnv, { session });
  const [hostSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  client = new Client({ name: "a-host", version: "1" });
  await client.connect(hostSide);
  return client;
}

function textOf(result: Awaited<ReturnType<Client["callTool"]>>): string {
  return (result.content as { type: string; text: string }[])[0]!.text;
}

describe("the server", () => {
  it("lists every tool, each with its manual in its description and `prod` in its schema", async () => {
    const host = await connected(project());
    const { tools } = await host.listTools();
    expect(tools.map((one) => one.name).sort()).toEqual(TOOLS.map((one) => one.name).sort());
    const whoami = tools.find((one) => one.name === "whoami")!;
    expect(whoami.description).toContain("it proves the project's key and names the org");
    expect(Object.keys(whoami.inputSchema.properties ?? {})).toEqual(["prod"]);
  });

  it("answers a call as JSON, in the env asked, every secret it knows of hidden", async () => {
    const sent = answer("get", "/v1/whoami", { ...WHO, env: "production" });
    const host = await connected(project());
    const result = await host.callTool({ name: "whoami", arguments: { prod: true } });
    expect(result.isError).toBeFalsy();
    const said = JSON.parse(textOf(result)) as Record<string, unknown>;
    expect(said).toMatchObject({ org: "clinica", gateway: GATEWAY, environment: "production", key_from: "the environment", production_allowed_for_this_key: false });
    expect(textOf(result)).not.toContain(KEY);
    expect(said["person"]).toBe("Ana, whose key is ***");
    expect(sent[0]!.env).toBe("production");
  });

  it("with no project open refuses in one sentence naming the tool that opens one", async () => {
    const host = await connected(undefined);
    const result = await host.callTool({ name: "whoami", arguments: {} });
    expect(result.isError).toBe(true);
    expect(textOf(result)).toMatch(/^no project open: call `project`/);
  });

  it("an argument its schema refuses is the field and what is wrong with it", async () => {
    const host = await connected(project());
    const result = await host.callTool({ name: "numbers", arguments: { action: "steal" } });
    expect(result.isError).toBe(true);
    expect(textOf(result)).toMatch(/action/);
  });

  it("the gateway's refusal is its sentence, scrubbed", async () => {
    const host = await connected(project());
    refuse("get", "/v1/whoami", 401, `the key ${KEY} was revoked`);
    const result = await host.callTool({ name: "whoami", arguments: {} });
    expect(result.isError).toBe(true);
    expect(textOf(result)).toBe("the gateway answered 401: the key *** was revoked");
  });
});
