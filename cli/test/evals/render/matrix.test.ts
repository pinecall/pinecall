/** The matrix as a terminal reads it: each golden marked `file` or `case` when the suite knows what it sent, unmarked when nobody does. */

import { describe, expect, it } from "vitest";

import { matrix, suite } from "../../../src/evals/render/matrix.js";
import { aRun } from "../../support/fixtures.js";

const AS = "the app's own model";

describe("where a golden came from", () => {
  it("is `file` for one this side sent, `case` for one it did not, and nothing when it is not known", () => {
    expect(matrix(aRun(), {}, AS, new Set(["books-thursday"]))[1]).toBe("  ✓ books-thursday  file");
    expect(matrix(aRun(), {}, AS, new Set())[1]).toBe("  ✓ books-thursday  case");
    expect(matrix(aRun(), {}, AS)[1]).toBe("  ✓ books-thursday");
  });

  it("stays on the line of a golden that broke, before its details", () => {
    const lines = matrix(aRun([{ metric: "tools", passed: false, reason: "never booked" }]), {}, AS, new Set());
    expect(lines[1]).toBe("  ✗ books-thursday  case");
    expect(lines[2]).toContain("tools  broken   never booked");
  });

  it("a suite's report marks from the files it sent, and the latencies follow the mark", () => {
    const report = { run: aRun(), latencies: { call_g1: { e2e_latency: 1.2 } }, reproductions: [], held: true, files: ["books-thursday"] };
    expect(suite(report, AS)[1]).toBe("  ✓ books-thursday  file  e2e_latency 1200ms");
  });
});
