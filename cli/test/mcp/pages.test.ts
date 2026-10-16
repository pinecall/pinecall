/** docs/mcp/ is what scripts/mcp-pages writes from the tools: a page that drifted from a tool's schema or manual fails here. */

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { examples, PAGES, pageOf } from "../../scripts/mcp-pages.js";
import { STAGES } from "../../src/mcp/tools/index.js";

describe("the MCP pages", () => {
  const kept = examples();
  for (const stage of STAGES) {
    it(`docs/mcp/${stage.page}.md is written from its tools`, () => {
      expect(readFileSync(`${PAGES}${stage.page}.md`, "utf8")).toBe(pageOf(stage, kept));
    });
  }
  it("every example names a tool that exists", () => {
    const names = new Set(STAGES.flatMap((stage) => stage.tools.map((tool) => tool.name)));
    expect(Object.keys(kept).filter((name) => !names.has(name))).toEqual([]);
  });
});
