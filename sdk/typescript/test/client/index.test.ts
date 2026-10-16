// Pins the exports of `@pinecall/agents/client` and `@pinecall/agents/client/testing`.

import { describe, expect, it } from "vitest";

import * as client from "../../src/client/index.js";
import * as testing from "../../src/client/testing/index.js";

// Sorted.
const PUBLIC = [
  "Agent",
  "Call",
  "CallBook",
  "Connection",
  "DevRefused",
  "Listeners",
  "Pinecall",
  "PinecallError",
  "Refused",
  "aLostSocket",
  "agentLogUrl",
  "appsUrl",
  "callLogUrl",
  "camelEvent",
  "feedUrl",
  "frame",
  "history",
  "lookupUrl",
  "nextId",
  "observe",
  "signed",
  "sseFrames",
];

// Test doubles; never imported by a published app at runtime.
const TESTING = ["FakeGateway", "FakeLog"];

describe("@pinecall/agents/client", () => {
  it("exports exactly what is listed here", () => {
    expect(Object.keys(client).sort()).toEqual(PUBLIC);
  });

  it("keeps the fakes on their own door", () => {
    expect(Object.keys(testing).sort()).toEqual(TESTING);
    for (const name of TESTING) expect(PUBLIC).not.toContain(name);
  });
});
