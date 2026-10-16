// The client socket: auth, register, re-register on reconnect, and close.

import { hostname } from "node:os";

import { afterEach, describe, expect, it, vi } from "vitest";
import { Pinecall, Refused } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

const KEY = "pk_test";

let gateway: FakeGateway;
let client: Pinecall | null = null;
let open: FakeGateway | null = null;

afterEach(async () => {
  client?.close();
  client = null;
  await open?.close();
  open = null;
});

async function connected(options: Partial<ConstructorParameters<typeof Pinecall>[0]> = {}, taken: string[] = []): Promise<Pinecall> {
  gateway = open = await FakeGateway.start({ apiKey: KEY, taken });
  client = new Pinecall({ url: gateway.url, apiKey: KEY, ...options });
  return client;
}

describe("connecting", () => {
  it("claims the slug and sends its declaration, naming the sdk, and claims no door", async () => {
    const pc = await connected();
    pc.agent("clinica-norte", { greeting: { say: "Clínica Norte, ¿en qué puedo ayudarte?" } });
    await pc.connect();

    const [register] = gateway.commandsOf("agent.register");
    expect(register?.agent).toBe("clinica-norte");
    // Always empty; kept on the wire for older gateways.
    expect(register?.data["routes"]).toEqual([]);
    expect(register?.data["sdk"]).toMatch(/^pinecall\//);
    expect(register?.data["host"]).toBe(hostname());

    const [configure] = gateway.commandsOf("agent.configure");
    expect(configure?.data["config"]).toMatchObject({ greeting: { say: "Clínica Norte, ¿en qué puedo ayudarte?" } });
  });

  // Never reads env, so an unrelated exported key (e.g. v1's SDK) cannot be picked up.
  it("refuses to start without a url and a key, and looks in no environment for either", () => {
    process.env["PINECALL_API_KEY"] = "pk_v1s_key_still_exported_in_this_shell";
    process.env["PINECALL_URL"] = "https://somebody-elses-gateway.test";
    try {
      expect(() => new Pinecall({ url: "http://127.0.0.1:1" })).toThrow(/url, apiKey/);
      expect(() => new Pinecall()).toThrow(/url, apiKey/);
    } finally {
      delete process.env["PINECALL_API_KEY"];
      delete process.env["PINECALL_URL"];
    }
  });

  it("never opens, and learns nothing, when the key is wrong", async () => {
    gateway = open = await FakeGateway.start({ apiKey: KEY });
    client = new Pinecall({ url: gateway.url, apiKey: "pk_wrong" });
    client.onErrors(() => undefined);
    await expect(client.connect()).rejects.toThrow(/403/);
  });

  it("hears the registry refuse a slug it will not hand over", async () => {
    const pc = await connected({}, ["clinica-norte"]);
    pc.onErrors(() => undefined);
    pc.agent("clinica-norte", {});
    await expect(pc.connect()).rejects.toBeInstanceOf(Refused);
  });

  it("declares itself again after the gateway drops it", async () => {
    const pc = await connected({ backoff: { firstMs: 20, capMs: 40 } });
    pc.onErrors(() => undefined);
    pc.agent("clinica-norte", {});
    await pc.connect();
    expect(gateway.commandsOf("agent.register")).toHaveLength(1);

    gateway.cut();
    await vi.waitFor(() => expect(gateway.commandsOf("agent.register")).toHaveLength(2), { timeout: 4_000 });
    expect(gateway.commandsOf("agent.configure")).toHaveLength(2);
  });

  it("pings while it is up", async () => {
    const pc = await connected({ pingMs: 20 });
    pc.agent("clinica-norte", {});
    await pc.connect();
    await vi.waitFor(() => expect(gateway.commandsOf("ping").length).toBeGreaterThan(1), { timeout: 4_000 });
  });
});

describe("being stopped", () => {
  it("hears why, closes, and never dials back", async () => {
    const pc = await connected({ backoff: { firstMs: 10, capMs: 20 } });
    pc.agent("clinica-norte", {});
    const heard: string[] = [];
    pc.onStopped((why) => heard.push(why));
    await pc.connect();

    gateway.stop("stopped by Ana");
    await vi.waitFor(() => expect(heard).toEqual(["stopped by Ana"]));
    await new Promise((waited) => setTimeout(waited, 100));

    expect(pc.connected).toBe(false);
    expect(gateway.connections).toBe(0);
    expect(gateway.commandsOf("agent.register")).toHaveLength(1);
  });

  it("says it on the error door when nobody listens for a stop", async () => {
    const pc = await connected();
    const errors: string[] = [];
    pc.onErrors((error) => errors.push(error.message));
    pc.agent("clinica-norte", {});
    await pc.connect();

    gateway.stop("stopped by Ana");
    await vi.waitFor(() => expect(errors).toContain("stopped by Ana"));
  });
});

// A 1008 close carries the gateway's reason: surface it, and do not retry.
describe("a socket the gateway refuses", () => {
  it("carries the gateway's own sentence, and is not retried", async () => {
    const said = "this key does not open app: it opens calls · evals";
    const refusing = await FakeGateway.start({ refusesWith: said });
    const pc = new Pinecall({ url: refusing.url, apiKey: "pk_test_whatever", backoff: { firstMs: 10, capMs: 20 } });
    const heard: string[] = [];
    pc.onErrors((failed) => heard.push(failed.message));
    try {
      await pc.connect().catch((failed: unknown) => heard.push(failed instanceof Error ? failed.message : String(failed)));
      await vi.waitFor(() => expect(heard.some((line) => line.includes(said))).toBe(true));
      await new Promise((waited) => setTimeout(waited, 60));

      expect(refusing.connections).toBe(0);
    } finally {
      pc.close();
      await refusing.close();
    }
  });
});
