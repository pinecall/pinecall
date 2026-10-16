/** A tool as declared: `prod` added to its schema and taken out before its handler, its arguments checked first. */

import { describe, expect, it } from "vitest";
import { z } from "zod";

import { tool, ToolRefused } from "../../src/mcp/tool.js";
import type { ToolContext } from "../../src/mcp/tool.js";

const echo = tool({
  name: "echo",
  description: "says it back",
  schema: { text: z.string().min(1) },
  manual: "`echo` says it back.",
  handler: async (args) => args,
});

describe("a tool", () => {
  it("takes prod beside its own fields, and its handler never sees it", async () => {
    expect(Object.keys(echo.schema)).toEqual(["text", "prod"]);
    expect(await echo.call({ text: "hi", prod: true }, {} as ToolContext)).toEqual({ text: "hi" });
  });

  it("refuses what its schema refuses before its handler runs", async () => {
    expect(() => echo.call({ text: "" }, {} as ToolContext)).toThrow();
  });

  it("a refusal is one of ours, its words the whole answer", () => {
    expect(new ToolRefused("no").message).toBe("no");
  });
});
