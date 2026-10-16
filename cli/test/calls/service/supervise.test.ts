/** A supervisor's desk: a typed line as a move, the call's entries as the desk reads them, a move sent, an ended call refused. */

import { describe, expect, it } from "vitest";

import * as service from "../../../src/calls/service/supervise.js";
import { UsageError } from "../../../src/errors.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";

describe("a typed line", () => {
  it("is a move, leaving, or nothing", () => {
    expect(service.moveOf("w offer Thursday")).toEqual({ verb: "whisper", text: "offer Thursday" });
    expect(service.moveOf("s One moment, please.")).toEqual({ verb: "say", text: "One moment, please." });
    expect(service.moveOf("t")).toEqual({ verb: "takeover" });
    expect(service.moveOf("x")).toEqual({ verb: "release" });
    expect(service.moveOf("e")).toEqual({ verb: "end", reason: undefined });
    expect(service.moveOf("e caller asked")).toEqual({ verb: "end", reason: "caller asked" });
    expect(service.moveOf("q")).toBe("leave");
    expect(service.moveOf("w")).toBeNull();
    expect(service.moveOf("hello")).toBeNull();
  });
});

describe("the call", () => {
  it("that ended is refused by name, with where to read it", async () => {
    answer("get", "/v1/calls/:call/state", { live: false, last_seq: 90 });
    const { ctx } = testContext();
    await expect(service.liveCall(ctx, "call_1")).rejects.toThrow(new UsageError(service.ALREADY_ENDED("call_1")));
    expect(service.ALREADY_ENDED("call_1")).toContain("`pinecall sessions call_1`");
  });

  it("is read as the desk reads it: turns, tools, the desk's own moves, the end; the rest left out", () => {
    const at = (type: string, data: Record<string, unknown>) => service.seenOf({ seq: 7, type, data });
    expect(at("turn.user", { text: "Hi" })).toEqual({ seq: 7, caller: "Hi" });
    expect(at("turn.agent", { text: "Hello" })).toEqual({ seq: 7, agent: "Hello" });
    expect(at("tool.call", { name: "book", arguments: { day: "thu" } })).toEqual({ seq: 7, tool: "book", args: { day: "thu" } });
    expect(at("supervisor.whisper", { text: "offer Thursday" })).toEqual({ seq: 7, desk: "whisper", said: "offer Thursday" });
    expect(at("supervisor.takeover", {})).toEqual({ seq: 7, desk: "takeover", said: null });
    expect(at("call.ended", { reason: "caller_hung_up" })).toEqual({ seq: 7, ended: "caller_hung_up" });
    expect(at("call.metrics", {})).toBeUndefined();
  });

  it("watched answers what was said since the cursor, and where to read on", async () => {
    answer("get", "/v1/calls/:call/state", { live: true, last_seq: 12 });
    const sent = answer("get", "/v1/calls/:call/events", {
      entries: [
        { seq: 11, type: "agent.state", data: { state: "thinking" } },
        { seq: 12, type: "turn.agent", data: { text: "Thursday at ten?" } },
      ],
      next: 12,
    });
    const { ctx } = testContext();
    expect(await service.watchCall(ctx, "call_1", 10, 1)).toEqual({ call: "call_1", live: true, lines: [{ seq: 12, agent: "Thursday at ten?" }], next: 12 });
    expect(sent[0]!.query).toMatchObject({ after: "10", limit: "200" });
  });

  it("a move is posted to the call's verbs", async () => {
    const sent = answer("post", "/v1/calls/:call/verbs");
    const { ctx } = testContext();
    await service.sendMove(ctx, "call_1", { verb: "whisper", text: "offer Thursday" });
    expect(sent[0]!.body).toEqual({ verb: "whisper", text: "offer Thursday" });
  });
});
