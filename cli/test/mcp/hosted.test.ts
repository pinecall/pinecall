/** The server as Pinecall hosts it: only the tools that act on no machine, on the key a request carried, a folder asked for refused. */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { afterEach, describe, expect, it } from "vitest";

import { HOSTED_STAGES, hostedServer, HostedSession, KEY_SOURCE, NAME_THE_AGENT, NO_FOLDER, whoHolds } from "../../src/mcp/hosted.js";
import { TOOLS } from "../../src/mcp/tools/index.js";
import { answer, GATEWAY, KEY, refuse } from "../support/gateway.js";

const WHO = { org: "org_1", slug: "clinica", key_id: "k_1", label: "Claude", env: "sandbox", name: "Ana", production: true };
// What acts on the machine a server runs on: a folder, a process, a file, a sign-in kept there.
const THE_MACHINES = ["login", "project", "runtime", "start", "stop", "status", "prompt", "voice_sample", "line", "remember"];
const META = { securitySchemes: [{ type: "oauth2", scopes: ["pinecall"] }] };

let client: Client | undefined;

afterEach(async () => {
  await client?.close();
  client = undefined;
});

/** A host connected to a hosted server for one key. */
async function connected(key = KEY): Promise<Client> {
  const server = hostedServer(new HostedSession(GATEWAY, key), { meta: META });
  const [hostSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  client = new Client({ name: "a-connector", version: "1" });
  await client.connect(hostSide);
  return client;
}

function textOf(result: Awaited<ReturnType<Client["callTool"]>>): string {
  return (result.content as { type: string; text: string }[])[0]!.text;
}

describe("the hosted server", () => {
  it("offers every tool but the ones that act on a machine, and says so in its instructions", async () => {
    const host = await connected();
    const { tools } = await host.listTools();
    const offered = tools.map((one) => one.name).sort();
    expect(offered).toEqual(TOOLS.map((one) => one.name).filter((name) => !THE_MACHINES.includes(name)).sort());
    expect(offered).toEqual(HOSTED_STAGES.flatMap((stage) => stage.tools.map((one) => one.name)).sort());
    expect(host.getInstructions()).toContain("This is Pinecall's hosted server");
    expect(host.getInstructions()).not.toContain("`login`");
  });

  it("tells a host which tools only read, and what it was told to say of every one", async () => {
    const host = await connected();
    const { tools } = await host.listTools();
    const reads = tools.filter((one) => one.annotations?.readOnlyHint === true).map((one) => one.name);
    expect(reads).toEqual(expect.arrayContaining(["whoami", "calls", "call", "docs_search", "get_doc"]));
    expect(reads).not.toEqual(expect.arrayContaining(["agent"]));
    expect(reads).not.toEqual(expect.arrayContaining(["dial"]));
    for (const one of tools) expect(one._meta).toEqual(META);
  });

  it("titles every tool and says of each whether it only reads or may take something away, as a directory requires", async () => {
    const host = await connected();
    const { tools } = await host.listTools();
    for (const one of tools) {
      expect(one.title, one.name).toBeTruthy();
      expect(one.annotations?.title, one.name).toBe(one.title);
      expect(typeof one.annotations?.readOnlyHint, one.name).toBe("boolean");
      if (one.annotations?.readOnlyHint === false) expect(typeof one.annotations.destructiveHint, one.name).toBe("boolean");
    }
    const kind = (name: string) => tools.find((one) => one.name === name)!.annotations;
    expect(kind("dial")).toMatchObject({ readOnlyHint: false, destructiveHint: true });
    expect(kind("chat")).toMatchObject({ readOnlyHint: false, destructiveHint: false });
    expect(kind("calls")).toMatchObject({ readOnlyHint: true });
  });

  it("speaks of this connection, never of a folder or this machine, where the local manual would", async () => {
    const host = await connected();
    const { tools } = await host.listTools();
    for (const one of tools) {
      expect(one.description, one.name).not.toMatch(/this machine is signed in|the project's key|agents\/<agent>/);
    }
    expect(tools.find((one) => one.name === "whoami")!.description).toContain("names the org this connection acts in");
  });

  it("runs a call on the key its session was made with, in the env asked, the key hidden", async () => {
    const sent = answer("get", "/v1/whoami", { ...WHO, name: `Ana, whose key is ${KEY}`, env: "production" });
    const host = await connected();
    const result = await host.callTool({ name: "whoami", arguments: { prod: true } });
    expect(result.isError).toBeFalsy();
    expect(JSON.parse(textOf(result))).toMatchObject({ org: "clinica", gateway: GATEWAY, environment: "production", key_from: KEY_SOURCE, person: "Ana, whose key is ***" });
    expect(sent[0]).toMatchObject({ env: "production", authorization: `Bearer ${KEY}` });
  });

  it("takes the agent by its name, with no folder to read one from", async () => {
    const sent = answer("get", "/v1/agents/:slug/pipeline", { stages: [] });
    const host = await connected();
    const named = await host.callTool({ name: "pipeline", arguments: { agent: "front-desk" } });
    expect(named.isError).toBeFalsy();
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/pipeline");
    const unnamed = await host.callTool({ name: "pipeline", arguments: {} });
    expect(unnamed.isError).toBe(true);
    expect(textOf(unnamed)).toBe(NAME_THE_AGENT);
    const talked = await host.callTool({ name: "chat", arguments: { action: "say", text: "hello" } });
    expect(textOf(talked)).toBe(NAME_THE_AGENT);
  });

  it("reads an agent's personas by its name: the folder is asked for only by what is kept as code", async () => {
    const sent = answer("get", "/v1/agents/:slug/personas", { personas: [] });
    const host = await connected();
    const listed = await host.callTool({ name: "personas", arguments: { action: "list", agent: "front-desk" } });
    expect(listed.isError).toBeFalsy();
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/personas");
  });

  it("refuses what reads or writes an agent's files, naming the server that does it", async () => {
    const host = await connected();
    for (const asked of [
      { name: "docs", arguments: { action: "push", agent: "front-desk" } },
      { name: "test", arguments: { action: "run", agent: "front-desk" } },
      { name: "runs", arguments: { action: "promote", agent: "front-desk", call: "call_1" } },
      { name: "deploy", arguments: { action: "deploy" } },
    ]) {
      const result = await host.callTool(asked);
      expect(result.isError).toBe(true);
      expect(textOf(result)).toBe(NO_FOLDER);
    }
  });

  it("a server's token acts in its own env alone", async () => {
    const host = await connected("pc_test_0123456789abcdef0123456789abcdef");
    const result = await host.callTool({ name: "whoami", arguments: { prod: true } });
    expect(result.isError).toBe(true);
    expect(textOf(result)).toMatch(/a sandbox server's token: it acts in sandbox alone/);
  });
});

describe("who holds a key", () => {
  it("is the gateway's word, and nobody for a key that opens nothing", async () => {
    answer("get", "/v1/whoami", WHO);
    expect(await whoHolds(GATEWAY, KEY)).toMatchObject({ org: "org_1", label: "Claude" });
    refuse("get", "/v1/whoami", 401, "this key opens nothing here");
    expect(await whoHolds(GATEWAY, KEY)).toBeNull();
  });

  it("a gateway that fails to answer is thrown, never taken for a refusal", async () => {
    refuse("get", "/v1/whoami", 503, "the database took too long");
    await expect(whoHolds(GATEWAY, KEY)).rejects.toThrow(/too long/);
  });
});
