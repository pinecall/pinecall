/** SseParser yields whole messages in order regardless of chunk boundaries. */

import { expect, test } from "vitest";

import { SseParser } from "../src/stream";

test("a message is its id, its event and its data lines joined, ended by a blank line", () => {
  const parser = new SseParser();
  const messages = parser.feed('id: 7\nevent: turn.user\ndata: {"seq":7,\ndata: "type":"turn.user"}\n\n');
  expect(messages).toEqual([{ id: "7", event: "turn.user", data: '{"seq":7,\n"type":"turn.user"}' }]);
});

test("a frame cut anywhere by the network is still one frame", () => {
  const parser = new SseParser();
  const whole = 'id: 1\nevent: call.started\ndata: {"a":1}\n\nid: 2\nevent: turn.user\ndata: {"b":2}\n\n';
  const out: unknown[] = [];
  for (const piece of whole.match(/.{1,5}/gs) ?? []) out.push(...parser.feed(piece));
  expect(out).toEqual([
    { id: "1", event: "call.started", data: '{"a":1}' },
    { id: "2", event: "turn.user", data: '{"b":2}' },
  ]);
});

test("a comment is kept alive and dropped, CRLF is a line end, and an id stands until replaced", () => {
  const parser = new SseParser();
  const first = parser.feed(": keep-alive\r\n\r\nid: 3\r\ndata: x\r\n\r\n");
  expect(first).toEqual([{ id: "3", event: null, data: "x" }]);
  const second = parser.feed("data: y\n\n");
  expect(second).toEqual([{ id: "3", event: null, data: "y" }]);
});
