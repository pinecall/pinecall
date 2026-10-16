/** Where a verb writes: the result as JSON or lines, and a collecting io for a caller that is no terminal. */

import { Writable } from "node:stream";

import { describe, expect, it } from "vitest";

import { CollectingIO, StreamIO } from "../../src/kit/io.js";

describe("io", () => {
  it("a result is the object under --json, the lines otherwise; print is silent under --json", () => {
    let out = "";
    const sink = new Writable({ write: (chunk, _encoding, done) => ((out += String(chunk)), done()) });
    const io = new StreamIO(sink, sink);
    io.result({ a: 1 }, () => ["one", "two"]);
    io.json = true;
    io.result({ a: 1 }, () => "unused");
    io.print("not under json");
    expect(out).toBe('one\ntwo\n{\n  "a": 1\n}\n');
  });

  it("a collecting io keeps the data and the lines, for a caller that is no terminal", () => {
    const io = new CollectingIO();
    io.result({ a: 1 }, () => "x");
    io.warn("careful");
    expect([io.results, io.lines]).toEqual([[{ a: 1 }], ["warning: careful"]]);
  });
});
