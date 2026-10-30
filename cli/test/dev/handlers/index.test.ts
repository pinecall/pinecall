/** The console's dev verbs this process answers: one table over every screen, every failure a refusal with a status the console reads. */

import { readFileSync } from "node:fs";

import { DevRefused } from "@pinecall/agents/client";
import { describe, expect, it } from "vitest";
import { z } from "zod";

import { devHandler, screensFor } from "../../../src/dev/handlers/index.js";
import { mine, refusalOf } from "../../../src/dev/handlers/screen.js";
import { servedByTheGateway } from "../../../src/dev/serving.js";
import { GatewayError, UsageError } from "../../../src/errors.js";
import { homeOf } from "../../../src/project/layout.js";
import { testContext } from "../../support/context.js";
import { project } from "../../support/project.js";

function here(files: Record<string, string> = {}) {
  const root = project(["front-desk"], files);
  return { ctx: testContext({ cwd: root }).ctx, home: homeOf(`${root}/agents/front-desk/agent.ts`), served: servedByTheGateway("front-desk") };
}

describe("the table", () => {
  it("answers a verb a screen holds, and refuses one nobody holds with 404", async () => {
    const answer = devHandler(screensFor(here({ "agents/front-desk/test/goldens/books.json": JSON.stringify({ turns: [{ say: "Thursday?" }], expect: { tools: ["book"] } }) })));
    expect(await answer("goldens.roster", {})).toEqual({ agent: "front-desk", goldens: [{ name: "books", turns: [{ say: "Thursday?" }], expect: { tools: ["book"] } }] });
    await expect(answer("nobody.holds" as never, {})).rejects.toMatchObject({ status: 404 });
  });

  it("writes a persona the console kept as a file the class reads", async () => {
    const root = project(["front-desk"]);
    const answer = devHandler(screensFor({ ctx: testContext({ cwd: root }).ctx, home: homeOf(`${root}/agents/front-desk/agent.ts`), served: servedByTheGateway("front-desk") }));
    const written = await answer("personas.write", { name: "price-shopper", goal: "get a price", style: "blunt", expects: ["The agent should give the price."] });
    expect(written).toEqual({ path: "agents/front-desk/test/personas/price-shopper.json", name: "price-shopper" });
    expect(JSON.parse(readFileSync(`${root}/agents/front-desk/test/personas/price-shopper.json`, "utf8"))).toEqual({ goal: "get a price", style: "blunt", expects: ["The agent should give the price."] });
    await expect(answer("personas.write", { name: "Price Shopper", goal: "g", style: "s" })).rejects.toMatchObject({ status: 422 });
  });

  it("a request about another agent is refused with where to run", async () => {
    const answer = devHandler(screensFor(here()));
    await expect(answer("goldens.run", { agent: "sales", goldens: ["books"] })).rejects.toMatchObject({ status: 409 });
  });
});

describe("a refusal", () => {
  it("keeps the gateway's status, makes an input's fault a 422, and anything else a 500", () => {
    expect(refusalOf(new GatewayError(403, "no"))).toMatchObject({ status: 403, detail: "no" });
    expect(refusalOf(z.object({ agent: z.string() }).safeParse({}).error)).toMatchObject({ status: 422, detail: expect.stringMatching(/^agent: /) });
    expect(refusalOf(new UsageError("bad"))).toMatchObject({ status: 422, detail: "bad" });
    expect(refusalOf(new Error("boom"))).toMatchObject({ status: 500, detail: "boom" });
    const already = new DevRefused(410, "gone");
    expect(refusalOf(already)).toBe(already);
  });

  it("names this process's agent and the one asked", () => {
    expect(() => mine(here(), "sales", "chat with")).toThrow("this process runs in front-desk's directory: to chat with sales, run `pinecall start` there");
  });
});
