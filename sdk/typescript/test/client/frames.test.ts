// Outgoing frames and their addressing.

import { describe, expect, it } from "vitest";
import { PinecallError, agentLogUrl, appsUrl, callLogUrl, frame } from "../../src/client/index.js";

describe("a command frame", () => {
  it("camelCases in and snake_cases out, and never touches the app's own JSON", () => {
    const command = frame("tool.result", "clinica-norte", "CA_1", { callId: "toolu_02", name: "book_slot", output: { slot_held: "10:15" }, durationS: 0.4 }, "c1");
    expect(command).toEqual({
      type: "tool.result",
      agent: "clinica-norte",
      call: "CA_1",
      id: "c1",
      data: { call_id: "toolu_02", name: "book_slot", output: { slot_held: "10:15" }, duration_s: 0.4 },
    });
  });

  it("refuses a shape the gateway would have refused, here, where the app can read it", () => {
    expect(() => frame("prompt.set", "clinica-norte", "CA_1", { region: "view", text: "" } as unknown as { name: string; text: string })).toThrow(PinecallError);
  });
});

describe("the doors", () => {
  it("speaks ws to the app socket and http to the log, keeping any prefix the host has", () => {
    expect(appsUrl("https://gateway.pinecall.io")).toBe("wss://gateway.pinecall.io/v1/apps");
    expect(appsUrl("http://127.0.0.1:8000/")).toBe("ws://127.0.0.1:8000/v1/apps");
    expect(appsUrl("wss://gateway.pinecall.io/edge")).toBe("wss://gateway.pinecall.io/edge/v1/apps");
    expect(callLogUrl("https://gateway.pinecall.io", "CA_8f4a2c")).toBe("https://gateway.pinecall.io/v1/calls/CA_8f4a2c/events");
    expect(agentLogUrl("wss://gateway.pinecall.io", "clinica-norte")).toBe("https://gateway.pinecall.io/v1/agents/clinica-norte/calls");
  });
});
