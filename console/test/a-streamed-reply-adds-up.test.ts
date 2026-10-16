// A written call logs one delta per agent.transcript; a chat bubble is their sum per reply.

import { type Entry } from "@pinecall/core/wire/envelope";
import { describe, expect, it } from "vitest";

import { repliesOf } from "../src/screens/chat/streaming.js";

let seq = 0;
function an(type: string, data: Record<string, unknown>): Entry {
  seq += 1;
  return { seq, ts: seq, call: "call_1", agent: "a", type, ephemeral: false, data } as unknown as Entry;
}

describe("the reply being written", () => {
  it("is every delta of its speech added up, not the last one alone", () => {
    const { streaming, settled } = repliesOf([
      an("agent.transcript", { speech_id: "s1", text: "Hi, ", final: false }),
      an("agent.transcript", { speech_id: "s1", text: "this is ", final: false }),
      an("agent.transcript", { speech_id: "s1", text: "Sam.", final: false }),
    ]);

    expect(streaming.get("s1")).toBe("Hi, this is Sam.");
    expect(settled.has("s1")).toBe(false);
  });

  it("is settled once the turn is written, and a second reply adds up on its own", () => {
    const { streaming, settled } = repliesOf([
      an("agent.transcript", { speech_id: "s1", text: "One.", final: false }),
      an("turn.agent", { speech_id: "s1", text: "One." }),
      an("agent.transcript", { speech_id: "s2", text: "Two ", final: false }),
      an("agent.transcript", { speech_id: "s2", text: "more.", final: false }),
    ]);

    expect(settled.has("s1")).toBe(true);
    expect(streaming.get("s2")).toBe("Two more.");
  });
});
