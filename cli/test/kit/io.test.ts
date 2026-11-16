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

  it("on a terminal an answer stands between two empty lines, written once; a pipe gets none", () => {
    let out = "";
    const sink = new Writable({ write: (chunk, _encoding, done) => ((out += String(chunk)), done()) });
    const terminal = new StreamIO(sink, sink, { tty: true });
    terminal.info("connecting");
    terminal.result({ a: 1 }, () => ["one", "two", "  → pinecall next", "  → pinecall other"]);
    terminal.over("three");
    terminal.end();
    // The next steps stand apart from the answer too.
    expect(out).toBe("\nconnecting\none\ntwo\n\n  → pinecall next\n  → pinecall other\n\rthree\n\n");
    out = "";
    // A verb that wrote nothing leaves the terminal as it was, and so does --json.
    const quiet = new StreamIO(sink, sink, { tty: true });
    quiet.end();
    quiet.json = true;
    quiet.result({ a: 1 }, () => "unused");
    quiet.end();
    expect(out).toBe('{\n  "a": 1\n}\n');
    out = "";
    // A turn that lands over a prompt takes the prompt's row: nothing goes before it, and the end closes it.
    const chat = new StreamIO(sink, sink, { tty: true });
    chat.over("› hello");
    chat.end();
    expect(out).toBe("\r› hello\n\n");
  });

  it("the help is written whole, its lines painted where the terminal takes colour", () => {
    let out = "";
    const sink = new Writable({ write: (chunk, _encoding, done) => ((out += String(chunk)), done()) });
    new StreamIO(sink, sink, { color: { out: true, err: false } }).page("Usage: pinecall data\n\nCommands:\n");
    expect(out).toBe("\u001b[1mUsage:\u001b[0m pinecall data\n\n\u001b[1mCommands:\u001b[0m\n");
  });

  it("a collecting io keeps the data and the lines, for a caller that is no terminal", () => {
    const io = new CollectingIO();
    io.result({ a: 1 }, () => "x");
    io.warn("careful");
    expect([io.results, io.lines]).toEqual([[{ a: 1 }], ["warning: careful"]]);
  });
});
