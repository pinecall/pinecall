/** Colour on a terminal: the marks and the next steps alone, never the data. */

import { describe, expect, it } from "vitest";

import { paintLine } from "../../src/kit/paint.js";

describe("paintLine", () => {
  it("colours a leading mark, dims a next step, reddens a refusal's pinecall, and leaves the rest", () => {
    expect(paintLine("  ✓ grounded")).toBe("  \u001b[32m✓\u001b[0m grounded");
    expect(paintLine("✗ 3 of 6 judges broke")).toBe("\u001b[31m✗\u001b[0m 3 of 6 judges broke");
    expect(paintLine("  → pinecall cases show <case>")).toBe("\u001b[2m  → pinecall cases show <case>\u001b[0m");
    expect(paintLine("pinecall: no verb \"deploi\"")).toBe("\u001b[31mpinecall:\u001b[0m no verb \"deploi\"");
    // A tool call in a transcript opens with the same arrow, at the line's start: it is data.
    expect(paintLine("→ takeMessage(name=Ana)")).toBe("→ takeMessage(name=Ana)");
    expect(paintLine("output-review · sandbox")).toBe("output-review · sandbox");
  });
});
