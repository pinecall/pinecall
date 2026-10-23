/** The `docs` tool: the base pulled into the folder through it, each file's standing answered with the lines a terminal would print. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { docs } from "../../../src/mcp/tools/knowledge.js";
import type { ToolContext } from "../../../src/mcp/tool.js";
import { testContext } from "../../support/context.js";
import { answer } from "../../support/gateway.js";
import { project } from "../../support/project.js";

function context(cwd: string): ToolContext {
  return Object.assign(testContext({ cwd }).ctx, { session: {} as ToolContext["session"] });
}

describe("the docs tool", () => {
  it("pull writes the base into agents/<agent>/docs/ and answers each file's standing", async () => {
    const root = project(["front-desk"], { "agents/front-desk/docs/old.md": "# Old" });
    answer("get", "/v1/knowledge/:base", { base: "front-desk", kept: true, files: [{ path: "hours.md", chars: 7, chunks: 1, pushed_at: 0 }] });
    answer("get", "/v1/knowledge/:base/files/*", { path: "hours.md", text: "# Hours", chunks: 1, pushed_at: 0 });
    const said = (await docs.call({ action: "pull" }, context(root))) as { files: { path: string; status: string }[]; said: string[] };
    expect(said.files.map((one) => [one.path, one.status])).toEqual([["hours.md", "written"], ["old.md", "kept"]]);
    expect(said.said).toEqual(["agents/front-desk/docs/hours.md  written", "agents/front-desk/docs/old.md    not in the base (kept)"]);
    expect(readFileSync(join(root, "agents/front-desk/docs/hours.md"), "utf8")).toBe("# Hours");
  });

  it("push writes the folder into the base with no query: the base's other files stay", async () => {
    const root = project(["front-desk"], { "agents/front-desk/docs/hours.md": "# Hours" });
    const sent = answer("put", "/v1/knowledge/:base", { base: "front-desk", chunks: 1, kept: 2, language: "english", took_ms: 10 });
    expect(await docs.call({ action: "push" }, context(root))).toMatchObject({ kept: 2, files: 1 });
    expect(sent[0]!.query).toEqual({});
  });
});
