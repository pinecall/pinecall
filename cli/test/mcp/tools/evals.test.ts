/** The `cases` tool: a golden written by hand added whole, never from a file; what `add` needs, refused by name before anything is sent. */

import { describe, expect, it } from "vitest";

import { cases } from "../../../src/mcp/tools/evals.js";
import type { ToolContext } from "../../../src/mcp/tool.js";
import { testContext } from "../../support/context.js";
import { answer } from "../../support/gateway.js";
import { A_CASE } from "../../support/fixtures.js";

const GOLDEN = { turns: [{ say: "How much is a crown?" }], expect: { not: ["euros"] } };

function context(): ToolContext {
  return Object.assign(testContext().ctx, { session: {} as ToolContext["session"] });
}

describe("the cases tool", () => {
  it("add puts the golden under its own name, or the name given, held out only when asked", async () => {
    const sent = answer("put", "/v1/agents/:slug/cases/:name", ({ path }) => ({ ...A_CASE, name: path.split("/").pop(), status: "approved", source: "person", source_call: null }));
    expect(await cases.call({ action: "add", golden: { ...GOLDEN, name: "no-price" } }, context())).toMatchObject({ name: "no-price", status: "approved", source: "person" });
    await cases.call({ action: "add", name: "crown-price", golden: GOLDEN, held_out: true }, context());
    expect(sent.map((one) => one.path)).toEqual(["/v1/agents/front-desk/cases/no-price", "/v1/agents/front-desk/cases/crown-price"]);
    expect(sent[0]!.body).toEqual({ golden: { ...GOLDEN, name: "no-price" } });
    expect(sent[1]!.body).toEqual({ golden: { ...GOLDEN, name: "crown-price" }, held_out: true });
  });

  it("add takes the golden itself and a name for one that has none, and reads no file", async () => {
    const sent = answer("put", "/v1/agents/:slug/cases/:name", A_CASE);
    await expect(cases.call({ action: "add", name: "no-price" }, context())).rejects.toThrow("add takes the golden itself, as JSON");
    await expect(cases.call({ action: "add", golden: GOLDEN }, context())).rejects.toThrow("name is needed");
    expect(sent).toHaveLength(0);
  });
});
