// Code is coloured as an editor colours it: comments across lines, keywords, strings, decorators, types and tags, every character kept.

import { describe, expect, it } from "vitest";

import { coloured, type Kind } from "../../src/pointer/syntax.js";

const kinds = (line: { text: string; kind: Kind }[]): [string, Kind][] => line.filter((piece) => piece.text.trim() !== "").map((piece) => [piece.text, piece.kind]);

describe("code coloured", () => {
  it("keeps every character of every line, in order", () => {
    const text = '/** A desk. */\nexport class Desk extends Agent {\n  @tool({ announce: "Checking." })\n  render() { return <p>Hi.</p>; }\n}';

    expect(coloured(text).map((line) => line.map((piece) => piece.text).join(""))).toEqual(text.split("\n"));
  });

  it("names keywords, types, decorators, strings, tags and this", () => {
    const [cls, field, tool, view] = coloured('export class Desk extends Agent {\n  stage = "identify";\n  @tool({ announce: "Checking." })\n  render() { return this.stage === "x" ? <p>Hi.</p> : null; }');

    expect(kinds(cls!)).toEqual([["export", "keyword"], ["class", "keyword"], ["Desk", "type"], ["extends", "keyword"], ["Agent", "type"], ["{", "plain"]]);
    expect(kinds(field!)).toContainEqual(['"identify"', "string"]);
    expect(kinds(tool!)).toContainEqual(["@tool", "decorator"]);
    expect(kinds(view!)).toEqual(expect.arrayContaining([["return", "keyword"], ["this", "self"], ["<p", "tag"], ["</p", "tag"], ["null", "keyword"]]));
  });

  it("carries a block comment from line to line until it ends", () => {
    const lines = coloured("/** You are the front desk.\n *  Short sentences. */\nexport class Desk {}");

    expect(kinds(lines[0]!)).toEqual([["/** You are the front desk.", "comment"]]);
    expect(kinds(lines[1]!)).toEqual([[" *  Short sentences. */", "comment"]]);
    expect(kinds(lines[2]!)[0]).toEqual(["export", "keyword"]);
  });
});
