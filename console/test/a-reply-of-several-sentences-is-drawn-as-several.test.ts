/** A reply with several utterances renders each one, not the last one repeated. */

import { describe, expect, it } from "vitest";

import { rowsOf } from "../src/screens/call/timeline-rows.js";

// One reply can log several `turn.agent` entries under one speech_id; item_id identifies each
// message. Looking turns up by speech_id alone drew the last one for every row.
const SPEECH = "speech_cc0bff";

const turn = (item: string, text: string) => ({
  role: "agent" as const,
  speech_id: SPEECH,
  item_id: item,
  text,
  interrupted: false,
  metrics: {},
});

const entry = (seq: number, item: string) => ({
  seq,
  type: "turn.agent",
  ts: seq,
  call: "call_1",
  agent: "sofia",
  ephemeral: false,
  data: { speech_id: SPEECH, item_id: item, text: "", interrupted: false, metrics: {} },
});

describe("a reply said in more than one sentence", () => {
  it("draws each sentence as itself", () => {
    const state = {
      turns: [turn("item_836", "Putting that down now."), turn("item_860", "Will you be home?")],
      tools: [],
      confirms: [],
    } as never;

    const rows = rowsOf([entry(836, "item_836"), entry(860, "item_860")] as never, state);

    expect(rows.map((row) => (row as { turn?: { text: string } }).turn?.text)).toEqual([
      "Putting that down now.",
      "Will you be home?",
    ]);
  });
});
