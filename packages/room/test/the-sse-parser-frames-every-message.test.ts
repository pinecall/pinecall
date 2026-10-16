// The parser under the follow, alone: whatever way the bytes are cut, the same messages come out.

import { describe, expect, it } from "vitest";

import { SseParser } from "../src/log/sse.js";

const WIRE = "retry: 1000\n\n: ping\n\nid: 1\nevent: call.started\ndata: {\"a\":1}\n\nid: 2\nevent: turn.user\ndata: one\ndata: two\n\n";

describe("the SSE parser", () => {
  it("frames every message, and says nothing for retry lines and comments", () => {
    expect(new SseParser().feed(WIRE)).toEqual([
      { id: "1", event: "call.started", data: '{"a":1}' },
      { id: "2", event: "turn.user", data: "one\ntwo" },
    ]);
  });

  it("frames the same messages however the chunks fall, one byte at a time included", () => {
    const parser = new SseParser();
    const messages = [...WIRE].flatMap((byte) => parser.feed(byte));

    expect(messages).toEqual(new SseParser().feed(WIRE));
  });

  it("reads CRLF and CR line ends as a line end", () => {
    const messages = new SseParser().feed("id: 7\r\nevent: pong\rdata: x\r\n\r\n");

    expect(messages).toEqual([{ id: "7", event: "pong", data: "x" }]);
  });

  it("keeps a message whose blank line has not arrived until it does", () => {
    const parser = new SseParser();

    expect(parser.feed("id: 3\nevent: turn.agent\ndata: half")).toEqual([]);
    expect(parser.feed("\n\n")).toEqual([{ id: "3", event: "turn.agent", data: "half" }]);
  });
});
