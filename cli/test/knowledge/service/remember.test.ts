/** Memory's extraction cases: read off disk, named by their files, filtered, and run on the gateway for the agent. */

import { describe, expect, it } from "vitest";

import { casesIn, matching } from "../../../src/knowledge/service/cases.js";
import * as service from "../../../src/knowledge/service/remember.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { folder, project, write } from "../../support/project.js";

const A_CASE = { said: [["caller", "I'm Ana, allergic to penicillin."], ["agent", "Noted, Ana."]], expect: { keeps: ["penicillin"] } };
const A_RUN = { agent: "front-desk", model: "claude-haiku-5-5", cases: 2, held: 2, took_ms: 1200, results: [] };

describe("the cases", () => {
  it("take their file's name, numbered when a file holds several; the goldens beside them are skipped", () => {
    const dir = folder();
    write(dir, "allergy.json", JSON.stringify(A_CASE));
    write(dir, "names.json", JSON.stringify([A_CASE, { ...A_CASE, name: "spelled" }]));
    write(dir, "memory.json", "[]");
    write(dir, "docs.json", "[]");
    expect(casesIn<{ name?: string }>([dir]).map((one) => one.name)).toEqual(["allergy", "names #1", "spelled"]);
  });

  it("are filtered by a part of their name, any case", () => {
    expect(matching([{ name: "Allergy" }, { name: "names" }], "ALL")).toEqual([{ name: "Allergy" }]);
    expect(matching([{ name: "a" }], undefined)).toEqual([{ name: "a" }]);
  });
});

describe("remember", () => {
  it("runs the agent's agents/<name>/test/memory/ on the gateway", async () => {
    const root = project(["front-desk"], { "agents/front-desk/test/memory/allergy.json": JSON.stringify(A_CASE), "agents/front-desk/test/memory/names.json": JSON.stringify(A_CASE) });
    const sent = answer("post", "/v1/agents/:slug/memory/extraction", A_RUN);
    const { ctx } = testContext({ cwd: root });
    expect(await service.remember(ctx, service.RememberInput.parse({ grep: "all" }))).toEqual(A_RUN);
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/memory/extraction");
    expect((sent[0]!.body as { cases: { name: string }[] }).cases.map((one) => one.name)).toEqual(["allergy"]);
  });

  it("says where cases belong when there are none, and when nothing matched", async () => {
    const { ctx } = testContext();
    await expect(service.remember(ctx, service.RememberInput.parse({}))).rejects.toThrow(/no extraction goldens at .*agents\/front-desk\/test\/memory/);
    const root = project(["front-desk"], { "agents/front-desk/test/memory/allergy.json": JSON.stringify(A_CASE) });
    await expect(service.remember(testContext({ cwd: root }).ctx, service.RememberInput.parse({ grep: "zzz" }))).rejects.toThrow("no case matched --grep zzz");
  });

  it("a project of several agents is told to name one", async () => {
    const { ctx } = testContext({ cwd: project(["front-desk", "sales"]) });
    await expect(service.remember(ctx, service.RememberInput.parse({}))).rejects.toThrow(/--agent front-desk or --agent sales/);
  });
});
