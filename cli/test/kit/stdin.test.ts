/** Piped stdin: a line a secret, or the whole of it. */

import { Readable } from "node:stream";

import { describe, expect, it } from "vitest";

import { allOf, linesOf } from "../../src/kit/stdin.js";

describe("stdin", () => {
  it("a pipe is one line a secret, in order; past the last, empty", async () => {
    const next = linesOf(Readable.from(["first\r\nsecond\n"]));
    expect([await next(), await next(), await next()]).toEqual(["first", "second", ""]);
  });

  it("read whole, its last newline dropped", async () => {
    expect(await allOf(Readable.from(["-----BEGIN-----\nabc\n"]))).toBe("-----BEGIN-----\nabc");
  });
});
