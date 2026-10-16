/** The dataset against the gateway: cases read whole, decided by name, pulled into the repository, kept; groups decided whole. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as dataset from "../../../src/evals/service/dataset.js";
import { UsageError } from "../../../src/errors.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { A_CASE } from "../../support/fixtures.js";
import { folder } from "../../support/project.js";

describe("cases", () => {
  it("are read with the defaults the gateway leaves out written in", async () => {
    const sent = answer("get", "/v1/evals/cases", { cases: [{ ...A_CASE, status: undefined }], pending: 1, pending_at_most: 50 });
    const { ctx } = testContext();
    const list = await dataset.listCases(ctx, "front-desk", "pending");
    expect(sent[0]!.query).toEqual({ agent: "front-desk", status: "pending" });
    expect(list.cases[0]).toMatchObject({ status: "approved", broke: [], source_version: null, kept_in_repo: false, decided_by: null });
    expect([list.pending, list.pending_at_most]).toEqual([1, 50]);
  });

  it("are decided by name, and an unknown name is refused naming it", async () => {
    answer("get", "/v1/evals/cases", { cases: [A_CASE] });
    const sent = answer("patch", "/v1/evals/cases/:id", { ...A_CASE, status: "dismissed" });
    const { ctx } = testContext();
    await dataset.dismissCase(ctx, "front-desk", "double-booked", { judgeWasWrong: "grounded", note: "the price was in the docs" });
    expect(sent[0]!.path).toBe("/v1/evals/cases/case_1");
    expect(sent[0]!.body).toEqual({ status: "dismissed", judge_was_wrong: "grounded", note: "the price was in the docs" });
    await expect(dataset.approveCase(ctx, "front-desk", "nope")).rejects.toThrow("front-desk has no case named nope");
  });

  it("refuses a note with no judge that was wrong: it would be dropped", async () => {
    const { ctx } = testContext();
    await expect(dataset.dismissCase(ctx, "front-desk", "double-booked", { note: "why" })).rejects.toThrow(UsageError);
  });

  it("pulled: the golden is written first, then the case marked kept in the repository", async () => {
    answer("get", "/v1/evals/cases", { cases: [A_CASE] });
    const sent = answer("patch", "/v1/evals/cases/:id", { ...A_CASE, kept_in_repo: true });
    const out = folder();
    const { ctx } = testContext();
    const pulled = await dataset.pullCase(ctx, "front-desk", "double-booked", out);
    expect(pulled.path).toBe(join(out, "double-booked.json"));
    expect(JSON.parse(readFileSync(pulled.path, "utf8"))).toEqual(A_CASE.golden);
    expect(sent[0]!.body).toEqual({ kept_in_repo: true });
  });

  it("a finished call kept as a case, held out only when asked", async () => {
    const sent = answer("post", "/v1/evals/cases", A_CASE);
    const { ctx } = testContext();
    await dataset.keepCall(ctx, dataset.KeepInput.parse({ call: "call_9", name: " double-booked " }));
    await dataset.keepCall(ctx, dataset.KeepInput.parse({ call: "call_9", name: "x", heldOut: true }));
    expect(sent.map((one) => one.body)).toEqual([{ call: "call_9", name: "double-booked" }, { call: "call_9", name: "x", held_out: true }]);
    expect(() => dataset.KeepInput.parse({ call: "call_9", name: " " })).toThrow(/keep names the case it makes/);
  });
});

describe("groups", () => {
  it("are told from a case by their id", () => {
    expect([dataset.isGroup("grp_1"), dataset.isGroup("double-booked")]).toEqual([true, false]);
  });

  it("are decided whole, a wrong judge said as a flag", async () => {
    const sent = answer("patch", "/v1/evals/groups/:id", { id: "grp_1" });
    const { ctx } = testContext();
    await dataset.decideGroup(ctx, "grp_1", false, { judgeWasWrong: true });
    expect(sent[0]!.body).toEqual({ status: "dismissed", judge_was_wrong: true });
  });
});
