/** Colour on a terminal: each line read for what it is, and a line of plain words left alone. */

import { describe, expect, it } from "vitest";

import { paintLine } from "../../src/kit/paint.js";

const E = "\u001b[";
const off = `${E}0m`;
const green = (text: string): string => `${E}32m${text}${off}`;
const red = (text: string): string => `${E}31m${text}${off}`;
const yellow = (text: string): string => `${E}33m${text}${off}`;
const cyan = (text: string): string => `${E}36m${text}${off}`;
const dim = (text: string): string => `${E}2m${text}${off}`;
const bold = (text: string): string => `${E}1m${text}${off}`;
const accent = (text: string): string => `${E}1;38;5;141m${text}${off}`;
const dot = dim(" · ");

describe("paintLine", () => {
  it("colours a leading mark, a next step's arrow and a refusal's pinecall", () => {
    expect(paintLine("  ✓ grounded")).toBe(`  ${green("✓")} grounded`);
    expect(paintLine("✗ 3 of 6 judges broke")).toBe(`${red("✗")} 3 of 6 judges broke`);
    expect(paintLine("  → pinecall cases show <case>")).toBe(`  ${cyan("→")} ${dim("pinecall cases show <case>")}`);
    expect(paintLine("  – no golden here")).toBe(dim("  – no golden here"));
    expect(paintLine('pinecall: no verb "deploi"')).toBe(`${E}1;31mpinecall:${off} no verb "deploi"`);
  });

  it("names what an answer is about, and dims what only separates", () => {
    expect(paintLine("output-review · sandbox")).toBe(`${accent("output-review")}${dot}${yellow("sandbox")}`);
    expect(paintLine("dental-front-desk · 2 files · 543 ms")).toBe(`${accent("dental-front-desk")}${dot}2 files${dot}${dim("543 ms")}`);
    // A count is no name.
    expect(paintLine("8 apps · 5 agents")).toBe(`8 apps${dot}5 agents`);
  });

  it("makes a table's header bold and paints a standing that is a cell of its own", () => {
    expect(paintLine("VENDOR     DOES         STANDING")).toBe(bold("VENDOR     DOES         STANDING"));
    expect(paintLine("anthropic  llm          ready")).toBe(`${cyan("anthropic")}  llm          ${green("ready")}`);
    expect(paintLine("brightside-dental  —  release 2 failed: the process exited")).toBe(
      `${cyan("brightside-dental")}  ${dim("—")}  release 2 ${red("failed")}: the process exited`,
    );
    // A row is named by its first cell alone, however narrow; a date is read last; a kind's name is no standing.
    expect(paintLine("2  2026-11-16 08:47  app.failed")).toBe(`${cyan("2")}  ${dim("2026-11-16 08:47")}  app.failed`);
    // The word inside a sentence is the sentence's.
    expect(paintLine("the agent is ready when you are")).toBe("the agent is ready when you are");
    expect(paintLine("               yours  team   production")).toBe(bold("               yours  team   production"));
  });

  it("colours a record's label, and the help's own", () => {
    expect(paintLine("  key   k_abc · berna-air")).toBe(`  ${cyan("key")}   k_abc${dot}berna-air`);
    expect(paintLine("  opens the sandbox, and production with --prod")).toBe("  opens the sandbox, and production with --prod");
    // A label of several parts is named by its first, and its date is read last.
    expect(paintLine('  v7 · Bernardo · 2026-11-16 09:58   temperature 0.3')).toBe(`  ${cyan("v7")}${dot}Bernardo${dot}${dim("2026-11-16 09:58")}   temperature 0.3`);
    expect(paintLine("Usage: pinecall data [options] [command]")).toBe(`${bold("Usage:")} pinecall data [options] [command]`);
    expect(paintLine("Commands:")).toBe(bold("Commands:"));
    expect(paintLine("  erase       one ended call, gone")).toBe(`  ${cyan("erase")}       one ended call, gone`);
    // A description that went on to a second line is words, not a header.
    expect(paintLine("                              gone for good")).toBe("                              gone for good");
  });

  it("tells the speakers of a transcript apart, and a tool from its answer", () => {
    expect(paintLine("› Good morning. How can I help?")).toBe(`${accent("›")} Good morning. How can I help?`);
    expect(paintLine("‹ a visit on Tuesday")).toBe(`${cyan("‹")} ${dim("a visit on Tuesday")}`);
    expect(paintLine('→ freeSlots({"day":"tuesday"})')).toBe(`${yellow("→ freeSlots")}${dim('({"day":"tuesday"})')}`);
    expect(paintLine('← freeSlots {"free":["9:00"]}')).toBe(`${dim("←")} ${yellow("freeSlots")}${dim(' {"free":["9:00"]}')}`);
  });

  it("marks a section of the prompt and one agent's lines among several", () => {
    expect(paintLine("── identity (static) ──")).toBe(cyan("── identity (static) ──"));
    expect(paintLine("<rules>")).toBe(dim("<rules>"));
    expect(paintLine("dental-billing    │   doors       web")).toBe(`${dim("dental-billing    │ ")}  ${cyan("doors")}       web`);
  });

  it("leaves an empty line, and a line that carries colour of its own, as they are", () => {
    expect(paintLine("")).toBe("");
    expect(paintLine(`${E}2m- Prefers mornings. · until 2026-11-01${off}`)).toBe(`${E}2m- Prefers mornings. · until 2026-11-01${off}`);
  });
});
