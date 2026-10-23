/** A simulation's edges: the persona in the gateway's shape, who plays it this run, the exit a score makes, and the call a refusal leaves. */

import { once } from "node:events";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { WebSocketServer } from "ws";

import { createContext } from "../../../src/context.js";
import { PinecallError, UsageError } from "../../../src/errors.js";
import { callerOf, playedBy, ranOn, requireHeld, simulate, SimulateInput, type Simulated } from "../../../src/evals/service/simulation.js";
import { CollectingIO } from "../../../src/kit/io.js";
import { A_PERSONA } from "../../support/fixtures.js";
import { KEY, server } from "../../support/gateway.js";
import { folder, project } from "../../support/project.js";

const SIMULATED: Simulated = { persona: "apurado", goal: "book", call: "call_1", agentTurns: 4, callerTurns: 4, line: null, medians: {}, score: null, unjudged: false };

describe("the caller", () => {
  it("leaves out what the persona did not set", () => {
    expect(callerOf({ ...A_PERSONA, facts: {} })).toEqual({ name: "apurado", goal: A_PERSONA.goal, style: A_PERSONA.style, behavior: A_PERSONA.behavior });
  });

  it("carries what it did", () => {
    expect(callerOf({ ...A_PERSONA, llm: "openai/gpt-5.4-mini", voice: "cartesia-luis", expects: ["is offered a slot"] })).toMatchObject({
      facts: { name: "Luis" },
      llm: "openai/gpt-5.4-mini",
      voice: "cartesia-luis",
      expects: ["is offered a slot"],
    });
  });
});

describe("who plays the caller this run", () => {
  const OWN = { ...A_PERSONA, llm: "openai/gpt-5.4-mini", tts: "cartesia", voice: "cartesia-luis" };

  it("is the persona's own when the run names nobody", () => {
    expect(playedBy(OWN, {})).toEqual(OWN);
  });

  it("is the run's model and voice over the persona's", () => {
    expect(playedBy(OWN, { llm: "google/gemini-3.5-flash-lite", tts: "google", callerVoice: "Puck" })).toMatchObject({ llm: "google/gemini-3.5-flash-lite", tts: "google", voice: "Puck" });
  });

  it("drops the persona's voice when the run names another vendor and no voice of it", () => {
    expect(playedBy(OWN, { tts: "google" })).toMatchObject({ tts: "google", voice: null });
  });
});

describe("who plays the caller, said when the call opens", () => {
  it("is what the run names and nothing when it names nobody", () => {
    expect(ranOn({})).toBeUndefined();
    expect(ranOn({ llm: "google/gemini-3.5-flash-lite", callerVoice: "Puck" })).toEqual({ llm: "google/gemini-3.5-flash-lite", voice: "Puck" });
    expect(ranOn({ tts: "google" })).toEqual({ tts: "google" });
  });
});

describe("the exit", () => {
  const scored = (score: Record<string, unknown>): Simulated => ({ ...SIMULATED, score: { judges: [], judge_calls: 0, ...score } as never });
  // What the gate throws for a simulation, or nothing.
  const refusedWith = (said: Simulated): PinecallError | undefined => {
    try {
      requireHeld(said);
    } catch (caught) {
      return caught as PinecallError;
    }
  };

  it("is 0 when every judge held, and for a call nobody asked to judge", () => {
    expect(refusedWith(SIMULATED)).toBeUndefined();
    expect(refusedWith(scored({ passed: true }))).toBeUndefined();
  });

  it("is 1 when a judge answered broken", () => {
    expect(refusedWith(scored({ passed: false }))).toMatchObject({ exit: 1, message: "a judge answered broken" });
  });

  it("is 2 for a call nobody judged, saying why: no judge on, the evals used up, only n/a, no score in time", () => {
    const why = (said: Simulated): string | undefined => refusedWith(said)?.message;
    expect(refusedWith(scored({ passed: null, not_judged: "no judge is on for this agent" }))).toBeInstanceOf(UsageError);
    expect(refusedWith(scored({ passed: null }))).toMatchObject({ exit: 2 });
    expect(why(scored({ not_judged: "no judge is on for this agent" }))).toBe("nobody judged this call: no judge is on for this agent");
    expect(why(scored({ passed: null, not_judged: "every judge run over this call failed and not one of them answered" }))).toContain("not one of them answered");
    expect(why(scored({ passed: null, judges: [{ name: "consent", verdict: "na" }] }))).toBe("nobody judged this call: no judge held or broke, the rest classified the call or did not apply");
    expect(why({ ...SIMULATED, unjudged: true })).toBe("nobody judged this call: no call.score came within a minute");
  });

  it("takes one to forty turns", () => {
    expect(SimulateInput.parse({ persona: "apurado" }).turns).toBe(15);
    expect(() => SimulateInput.parse({ persona: "apurado", turns: 41 })).toThrow();
  });
});

// A written call is one socket on the gateway's own port, and the caller's next line one request to it:
// msw is let go for this file, which asks the fake gateway nothing, and taken back after it.
beforeAll(() => server.close());
afterAll(() => server.listen({ onUnhandledFrame: "error" }));

let gateway: Server | undefined;
let sockets: WebSocketServer | undefined;

afterEach(() => {
  sockets?.close();
  gateway?.closeAllConnections();
  gateway?.close();
  gateway = undefined;
  sockets = undefined;
});

describe("the call's socket", () => {
  it("opens with the persona and who plays it this run, so the gateway refuses what it cannot run before the call exists", async () => {
    let opened = "";
    gateway = createServer();
    sockets = new WebSocketServer({ server: gateway });
    sockets.on("connection", (socket, request) => {
      opened = request.url ?? "";
      socket.close(4503, "xai has no key: the org brought none and the box holds none");
    });
    gateway.listen(0, "127.0.0.1");
    await once(gateway, "listening");
    const url = `http://127.0.0.1:${(gateway.address() as AddressInfo).port}`;
    const ctx = createContext({ io: new CollectingIO(), processEnv: { PINECALL_URL: url, PINECALL_KEY: KEY, PINECALL_HOME: folder() }, cwd: project() });
    await expect(simulate(ctx, { slug: "front-desk" }, A_PERSONA, SimulateInput.parse({ persona: "apurado", turns: 1, llm: "xai/grok-4" }))).rejects.toMatchObject({ status: 503 });
    const query = new URL(opened, "http://gateway").searchParams;
    expect(query.get("persona")).toBe("apurado");
    expect(JSON.parse(query.get("played_by") ?? "null")).toEqual({ llm: "xai/grok-4" });
  });
});

describe("a call a refusal leaves", () => {
  it("is hung up: the caller's model that has no key refuses the next line, and an open socket would hold the process and the call", async () => {
    let hungUp = false;
    gateway = createServer((_request, response) => {
      response.writeHead(503, { "content-type": "application/json" }).end(JSON.stringify({ detail: "xai has no key: the org brought none and the box holds none" }));
    });
    sockets = new WebSocketServer({ server: gateway });
    sockets.on("connection", (socket) => {
      socket.send(JSON.stringify({ seq: 1, type: "call.started", call: "call_1", data: {} }));
      socket.on("message", (raw) => {
        if ((JSON.parse(String(raw)) as { hangup?: boolean }).hangup !== true) return;
        hungUp = true;
        socket.close(1000, "");
      });
    });
    gateway.listen(0, "127.0.0.1");
    await once(gateway, "listening");
    const url = `http://127.0.0.1:${(gateway.address() as AddressInfo).port}`;
    const ctx = createContext({ io: new CollectingIO(), processEnv: { PINECALL_URL: url, PINECALL_KEY: KEY, PINECALL_HOME: folder() }, cwd: project() });
    await expect(simulate(ctx, { slug: "front-desk" }, A_PERSONA, SimulateInput.parse({ persona: "apurado", turns: 1 }))).rejects.toMatchObject({ status: 503, exit: 2 });
    expect(hungUp).toBe(true);
  });
});
