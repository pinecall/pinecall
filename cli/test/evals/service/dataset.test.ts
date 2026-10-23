/** The dataset against the gateway: cases read whole, decided by name, pulled into the repository, kept, a golden written by hand added; groups decided whole. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as dataset from "../../../src/evals/service/dataset.js";
import { GatewayError, UsageError } from "../../../src/errors.js";
import { answer, refuse } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { A_CASE } from "../../support/fixtures.js";
import { folder, write } from "../../support/project.js";

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

describe("a golden written by hand", () => {
  const written = (name: string | undefined) => ({ ...(name === undefined ? {} : { name }), turns: [{ say: "How much is a crown?" }], expect: { not: ["euros"] } });
  const kept = () => answer("put", "/v1/agents/:slug/cases/:name", ({ path }) => ({ ...A_CASE, name: decodeURIComponent(path.split("/").pop()!), source: "person", status: "approved", source_call: null }));

  it("is kept under its own name, else --name, else its file's basename, held out only when asked", async () => {
    const dir = folder();
    write(dir, "no-price.json", JSON.stringify(written(undefined)));
    write(dir, "renamed.json", JSON.stringify(written("says-the-dentist")));
    const sent = kept();
    const { ctx } = testContext();
    const added = await dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [join(dir, "no-price.json"), join(dir, "renamed.json")] }));
    expect(added.map((one) => one.name)).toEqual(["no-price", "says-the-dentist"]);
    expect(added[0]).toMatchObject({ status: "approved", source: "person", broke: [], kept_in_repo: false });
    expect(sent.map((one) => one.path)).toEqual(["/v1/agents/front-desk/cases/no-price", "/v1/agents/front-desk/cases/says-the-dentist"]);
    expect(sent[0]!.body).toEqual({ golden: { ...written(undefined), name: "no-price" } });
    await dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [join(dir, "no-price.json")], name: "crown-price", heldOut: true }));
    expect(sent[2]!.path).toBe("/v1/agents/front-desk/cases/crown-price");
    expect(sent[2]!.body).toEqual({ golden: { ...written(undefined), name: "crown-price" }, held_out: true });
  });

  it("a file of several goldens keeps each under its own name, and one with no name is refused", async () => {
    const dir = folder();
    write(dir, "prices.json", JSON.stringify([written("crown"), written("filling")]));
    write(dir, "unnamed.json", JSON.stringify([written("crown"), written(undefined)]));
    const sent = kept();
    const { ctx } = testContext();
    expect((await dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [join(dir, "prices.json")] }))).map((one) => one.name)).toEqual(["crown", "filling"]);
    await expect(dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [join(dir, "unnamed.json")] }))).rejects.toThrow(/has no name, and a list's goldens name themselves/);
    await expect(dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [join(dir, "prices.json")], name: "x" }))).rejects.toThrow(/--name names one case, and .* holds 2 goldens/);
    expect(sent).toHaveLength(2);
  });

  it("never takes a folder, nor --name for several files, and sends nothing first", async () => {
    const dir = folder();
    write(dir, "a.json", JSON.stringify(written(undefined)));
    write(dir, "b.json", JSON.stringify(written(undefined)));
    const sent = kept();
    const { ctx } = testContext();
    await expect(dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [dir] }))).rejects.toThrow(/is a folder: add takes golden files/);
    await expect(dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [join(dir, "a.json"), join(dir, "b.json")], name: "x" }))).rejects.toThrow("--name names one case");
    await expect(dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [join(dir, "nowhere.json")] }))).rejects.toThrow(UsageError);
    expect(sent).toHaveLength(0);
  });

  it("a name a call made is the gateway's 409, said as it is", async () => {
    const dir = folder();
    write(dir, "double-booked.json", JSON.stringify(written(undefined)));
    refuse("put", "/v1/agents/:slug/cases/:name", 409, "double-booked was made by call_9: a case a call made is not rewritten");
    const { ctx } = testContext();
    const failed = dataset.addCases(ctx, "front-desk", dataset.AddCasesInput.parse({ files: [join(dir, "double-booked.json")] }));
    await expect(failed).rejects.toBeInstanceOf(GatewayError);
    await expect(failed).rejects.toThrow("a case a call made is not rewritten");
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
