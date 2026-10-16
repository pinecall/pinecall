/** A written call: lines owed until heard and answered, a case's state, and the socket itself against a gateway of the test's own. */

import { once } from "node:events";
import type { AddressInfo } from "node:net";

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { WebSocketServer, type WebSocket } from "ws";

import { Chat, answered, NOTHING_OWED, owing, sent, stateOfCase, waitBack } from "../../../src/calls/service/chat.js";
import { createContext } from "../../../src/context.js";
import { CollectingIO } from "../../../src/kit/io.js";
import { KEY, server } from "../../support/gateway.js";
import { folder, project, write } from "../../support/project.js";

describe("what a chat owes", () => {
  it("lines sent together are heard one turn at a time, and answered when the agent listens again", () => {
    let owed = sent(sent(NOTHING_OWED));
    owed = owing(owed, { type: "turn.user" });
    expect(owed).toEqual({ lines: 1, answering: true });
    owed = owing(owed, { type: "agent.state", data: { state: "listening" } });
    owed = owing(owed, { type: "turn.user" });
    owed = owing(owed, { type: "agent.state", data: { state: "thinking" } });
    expect(answered(owed)).toBe(false);
    owed = owing(owed, { type: "agent.state", data: { state: "listening" } });
    expect(answered(owed)).toBe(true);
  });

  it("redials after a backoff that doubles up to five seconds", () => {
    expect([1, 2, 3, 4, 5].map(waitBack)).toEqual([500, 1000, 2000, 4000, 5000]);
  });

  it("opens in a case's state, the first unless one is named", () => {
    const file = write(folder(), "goldens.json", JSON.stringify([{ state: { patient: "Ana" } }, { state: { patient: "Luis" } }]));
    expect(stateOfCase(file, undefined)).toEqual({ patient: "Ana" });
    expect(stateOfCase(file, 1)).toEqual({ patient: "Luis" });
    expect(() => stateOfCase(file, 2)).toThrow(`${file} has no case 2`);
  });
});

/** A gateway of the test's own: the chat socket alone, on a port of its own, playing a scripted agent. */
let gateway: WebSocketServer | undefined;

// The chat socket is `ws` over a real upgrade: msw is let go for this file, which asks the fake gateway
// nothing, and taken back after it, so the setup's own close finds it listening.
beforeAll(() => server.close());
afterAll(() => server.listen({ onUnhandledFrame: "error" }));

afterEach(async () => {
  gateway?.close();
  gateway = undefined;
});

async function chatGateway(onLine: (socket: WebSocket, said: Record<string, unknown>) => void): Promise<{ url: string; asked: URL[]; headers: Record<string, string | string[] | undefined>[] }> {
  const asked: URL[] = [];
  const headers: Record<string, string | string[] | undefined>[] = [];
  gateway = new WebSocketServer({ host: "127.0.0.1", port: 0 });
  gateway.on("connection", (socket, request) => {
    asked.push(new URL(request.url ?? "/", "http://gateway"));
    headers.push(request.headers);
    socket.send(JSON.stringify({ seq: 1, type: "call.started", call: "call_1", data: {} }));
    socket.on("message", (raw) => onLine(socket, JSON.parse(String(raw)) as Record<string, unknown>));
  });
  await once(gateway, "listening");
  return { url: `http://127.0.0.1:${(gateway.address() as AddressInfo).port}`, asked, headers };
}

function contextAt(url: string) {
  return createContext({ io: new CollectingIO(), processEnv: { PINECALL_URL: url, PINECALL_KEY: KEY, PINECALL_HOME: folder() }, cwd: project() });
}

describe("the socket", () => {
  it("opens on the agent with the key in a header, says a line, and waits until it is answered", async () => {
    const { url, asked, headers } = await chatGateway((socket, said) => {
      if (said["hangup"] === true) return socket.close(1000, "");
      socket.send(JSON.stringify({ seq: 2, type: "turn.user", call: "call_1", data: { text: said["text"] } }));
      socket.send(JSON.stringify({ seq: 3, type: "turn.agent", call: "call_1", data: { text: "Of course." } }));
      socket.send(JSON.stringify({ seq: 4, type: "agent.state", call: "call_1", data: { state: "listening" } }));
    });
    const heard: string[] = [];
    const chat = await Chat.open(contextAt(url), { agent: "front-desk", contact: "+34600000001", state: { patient: "Ana" } }, { onEntry: (entry) => heard.push(entry.type) });
    expect(chat.call).toBe("call_1");
    expect(asked[0]!.pathname).toBe("/v1/chat");
    expect(Object.fromEntries(asked[0]!.searchParams)).toEqual({ agent: "front-desk", contact: "+34600000001", state: '{"patient":"Ana"}' });
    expect(headers[0]!["authorization"]).toBe(`Bearer ${KEY}`);
    await chat.sayAndWait("I'd like to change my appointment", 5_000);
    expect(chat.settled).toBe(true);
    expect(heard).toEqual(["call.started", "turn.user", "turn.agent", "agent.state"]);
    expect(await chat.end()).toBe("");
    expect(chat.ended).toBe(true);
  });

  it("a gateway that closes before the call opens is the refusal, in its words", async () => {
    gateway = new WebSocketServer({ host: "127.0.0.1", port: 0 });
    gateway.on("connection", (socket) => socket.close(4404, "no process holds front-desk"));
    await once(gateway, "listening");
    const url = `http://127.0.0.1:${(gateway.address() as AddressInfo).port}`;
    // 4000 plus the status: a 4404 is a name nothing answers to, exit 2 like any name typed wrong.
    await expect(Chat.open(contextAt(url), { agent: "front-desk" })).rejects.toMatchObject({ status: 404, exit: 2, message: "the gateway answered 404: no process holds front-desk" });
  });
});
