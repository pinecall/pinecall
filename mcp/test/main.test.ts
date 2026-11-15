/** The entry's two quick ends: the check an image is pushed on, and an environment that lacks an address. */

import { describe, expect, it } from "vitest";

import { main } from "../src/main.js";

describe("the entry", () => {
  it("checks that the tools are there, and leaves", async () => {
    expect(await main(["--check"], {})).toBe(0);
  });

  it("names what its environment lacks, and exits 2", async () => {
    expect(await main([], { PINECALL_URL: "https://cloud.example.com" })).toBe(2);
  });
});
