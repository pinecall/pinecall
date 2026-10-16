/** An agent's calls against the gateway: the list by slug, one call whole off its log's ending, a page of its log and where to read on. */

import { describe, expect, it } from "vitest";

import * as service from "../../../src/calls/service/sessions.js";
import { UsageError } from "../../../src/errors.js";
import { answer, refuse } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { folder } from "../../support/project.js";

describe("the list", () => {
  it("is the project's agent's, or the slug named from any folder, newest first as the gateway keeps it", async () => {
    const sent = answer("get", "/v1/agents/:slug/sessions", { calls: [] });
    await service.listSessions(testContext().ctx, { limit: 3 });
    await service.listSessions(testContext({ cwd: folder() }).ctx, { agent: "sales" });
    expect(sent.map((one) => [one.path, one.query])).toEqual([
      ["/v1/agents/front-desk/sessions", { limit: "3" }],
      ["/v1/agents/sales/sessions", {}],
    ]);
  });

  it("refuses more than a hundred", () => {
    expect(() => service.ListSessionsInput.parse({ limit: 101 })).toThrow();
  });
});

describe("one call", () => {
  it("is refused by name when the gateway has no such call", async () => {
    refuse("get", "/v1/calls/:call/state", 404, "no such call");
    const { ctx } = testContext();
    await expect(service.showCall(ctx, "call_typo")).rejects.toThrow(new UsageError(service.NO_SUCH_CALL("call_typo")));
  });

  it("reads only the ending's entries, page after page, and keeps the last of each", async () => {
    answer("get", "/v1/calls/:call/state", { live: false, last_seq: 900 });
    const pages = answer("get", "/v1/calls/:call/events", ({ query }) =>
      query["after"] === "0"
        ? { entries: [{ seq: 400, type: "call.summary", data: { outcome: "first" } }], next: 500 }
        : { entries: [{ seq: 880, type: "call.summary", data: { outcome: "booked" } }, { seq: 881, type: "call.score", data: { passed: true } }], next: null },
    );
    const { ctx } = testContext();
    expect(await service.showCall(ctx, "call_1")).toEqual({ call: "call_1", live: false, summary: { outcome: "booked" }, score: { passed: true } });
    expect(pages.map((one) => one.query)).toEqual([
      { after: "0", limit: "500", types: "call.summary,call.score" },
      { after: "500", limit: "500", types: "call.summary,call.score" },
    ]);
  });
});

describe("a page of the log", () => {
  it("of a call that is over says where to read on until the last seq, and nothing past it", async () => {
    answer("get", "/v1/calls/:call/state", { live: false, last_seq: 120 });
    answer("get", "/v1/calls/:call/events", ({ query }) => ({ entries: [], next: query["after"] === "0" ? 60 : 120 }));
    const { ctx } = testContext();
    expect((await service.readLog(ctx, service.ReadLogInput.parse({ call: "call_1", limit: 60 }))).next).toBe(60);
    expect((await service.readLog(ctx, service.ReadLogInput.parse({ call: "call_1", after: 60, limit: 60 }))).next).toBeNull();
  });

  it("of a live call always says where to read on", async () => {
    answer("get", "/v1/calls/:call/state", { live: true, last_seq: 40 });
    answer("get", "/v1/calls/:call/events", { entries: [], next: 40 });
    const { ctx } = testContext();
    expect(await service.readLog(ctx, service.ReadLogInput.parse({ call: "call_1", after: 40 }))).toEqual({ call: "call_1", entries: [], next: 40, live: true });
  });

  it("sends the types kept, and an empty page past the end reads as none", async () => {
    answer("get", "/v1/calls/:call/state", { live: false, last_seq: 10 });
    const sent = answer("get", "/v1/calls/:call/events", null);
    const { ctx } = testContext();
    expect((await service.readLog(ctx, service.ReadLogInput.parse({ call: "call_1", after: 10, types: ["turn.user", "tool.call"] }))).entries).toEqual([]);
    expect(sent[0]!.query).toEqual({ after: "10", limit: "200", types: "turn.user,tool.call" });
  });
});
