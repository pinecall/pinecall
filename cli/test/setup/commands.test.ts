/** `pinecall setup` as typed: a project whose key points at another host is not this machine's to scan. */

import { describe, expect, it } from "vitest";

import { GATEWAY } from "../support/gateway.js";
import { run } from "../support/run.js";

describe("pinecall setup", () => {
  it("refuses to read this machine for a runtime on another host, naming it", async () => {
    const ran = await run(["setup", "--recommend"]);
    expect(ran.code).toBe(1);
    expect(ran.err).toContain(`this project talks to ${GATEWAY}`);
    expect(ran.err).toContain("runs on another host, so this machine is neither scanned nor set up");
    expect(ran.out).toBe("");
  });
});
