// Robustness of the test doubles.

import { connect, type Socket } from "node:net";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Pinecall } from "../../src/client/index.js";
import { FakeGateway } from "../../src/client/testing/index.js";

const KEY = "pk_test";

let gateway: FakeGateway | null = null;
let client: Pinecall | null = null;

afterEach(async () => {
  client?.close();
  client = null;
  await gateway?.close();
  gateway = null;
});

/** Open a raw socket and perform the WebSocket upgrade by hand. */
async function admitted(url: string): Promise<Socket> {
  const { hostname, port } = new URL(url);
  const socket = connect(Number(port), hostname);
  await new Promise<void>((resolve) => socket.once("connect", resolve));
  socket.write(
    `GET /v1/apps HTTP/1.1\r\nHost: ${hostname}:${port}\r\nAuthorization: Bearer ${KEY}\r\n` +
      "Upgrade: websocket\r\nConnection: Upgrade\r\n" +
      "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n",
  );
  await new Promise<void>((resolve) => socket.once("data", resolve));
  return socket;
}

describe("a fake gateway meeting traffic it cannot parse", () => {
  it("forgets that socket and keeps serving everybody else", async () => {
    gateway = await FakeGateway.start({ apiKey: KEY });
    const raw = await admitted(gateway.url);
    expect(gateway.connections).toBe(1);

    // Invalid frame (RSV1 set): `ws` emits `error`, which crashes the process if unhandled.
    raw.write(Buffer.from([0xc0, 0x00]));
    await vi.waitFor(() => expect(gateway?.connections).toBe(0));

    client = new Pinecall({ url: gateway.url, apiKey: KEY });
    client.agent("clinica-norte", { greeting: { say: "Clínica Norte, ¿en qué puedo ayudarte?" } });
    await client.connect();

    expect(gateway.commandsOf("agent.register")).toHaveLength(1);
    raw.destroy();
  });
});
