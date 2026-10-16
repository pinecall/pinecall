/** `pinecall prompt` runs offline, in no env: --prod is refused before anything is loaded. */

import { describe, expect, it } from "vitest";

import { run } from "../support/run.js";

describe("prompt", () => {
  it("refuses --prod with exit 2, in its own words, touching no agent", async () => {
    const ran = await run(["--prod", "prompt"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toMatch(/prompt runs offline, in no env: run it without --prod/);
  });
});
