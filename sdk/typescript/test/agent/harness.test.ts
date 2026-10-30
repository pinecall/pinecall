// The judges and the personas a class owns: the switches it declares, the files beside it read, and each refusal as a sentence.

import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { Agent, DeclarationRefused, judges, optionsFor, personas } from "../../src/index.js";
import { harnessOf, judgeOf, personaOf } from "../../src/agent/harness.js";

const OFFERS = `---
answer: verdict
when: always
reads: [facts]
---
Did the agent offer the next free slot before the caller asked twice?
`;

const RUSH = JSON.stringify({ goal: "book today", style: "short, interrupts", expects: ["The agent should offer today."], behavior: { interrupts: 0.3, pause_s: 1 } });

/** A folder shaped like `agents/<slug>/`, with the files given under `judges/` and `test/personas/`. */
function folder(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "harness-"));
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(join(dir, path, ".."), { recursive: true });
    writeFileSync(join(dir, path), text);
  }
  return dir;
}

describe("a judge file", () => {
  it("is read as the library writes one: front matter, then the question", () => {
    expect(judgeOf("judges/offers-next-slot.md", OFFERS)).toEqual({
      name: "offers-next-slot",
      question: "Did the agent offer the next free slot before the caller asked twice?",
      answer: "verdict",
      choices: [],
      when: "always",
      trigger: "",
      reads: ["facts"],
    });
  });

  it("takes the library's `on:` for when, and a comma-separated list", () => {
    const read = judgeOf("x.md", "---\non: simulations\nreads: prompt, evidence\n---\nWas it kind?");
    expect([read.when, read.reads]).toEqual(["simulations", ["prompt", "evidence"]]);
  });

  it.each([
    ["offers.md", "no front matter\n", "a judge opens with its front matter between two --- lines"],
    ["offers.md", "---\n\n---\n\n", "a judge asks a question of a call: write one below the front matter"],
    ["offers.md", "---\nanswer: maybe\n---\nQ?", 'answer is "maybe", not one of verdict, choice, score'],
    ["offers.md", "---\nanswer: choice\nchoices: [a]\n---\nQ?", "a judge that answers one of several needs at least two choices"],
    ["offers.md", "---\nchoices: [a, b]\n---\nQ?", "only a judge that answers one of several takes choices"],
    ["offers.md", "---\nwhen: trigger\n---\nQ?", "a judge that runs on a trigger needs the trigger's question"],
    ["offers.md", "---\nreads: dreams\n---\nQ?", 'reads is "dreams", not one of prompt, evidence, facts'],
    ["Offers Slot.md", "---\n\n---\nQ?", "\"Offers Slot\" is not a judge's name: lower-case words joined by hyphens"],
    ["offers.md", "---\nname: other\n---\nQ?", "its front matter says name: other, and the file is offers.md"],
  ])("%s refused: %s", (file, text, sentence) => {
    expect(() => judgeOf(file, text)).toThrow(DeclarationRefused);
    expect(() => judgeOf(file, text)).toThrow(sentence);
  });
});

describe("a persona file", () => {
  it("is what a PUT takes, under the file's name, with the wire's keys camelCased for the class", () => {
    expect(personaOf("test/personas/in-a-rush.json", RUSH)).toEqual({
      name: "in-a-rush",
      goal: "book today",
      style: "short, interrupts",
      expects: ["The agent should offer today."],
      behavior: { interrupts: 0.3, pauseS: 1 },
    });
  });

  it.each([
    ["in-a-rush.json", "{", "not JSON"],
    ["in-a-rush.json", "[]", "a persona is a JSON object with a goal and a style"],
    ["in-a-rush.json", '{"style": "s"}', "a persona wants something: write its goal, in the first person"],
    ["in-a-rush.json", '{"goal": "g"}', "a persona talks some way: write its style"],
    ["in-a-rush.json", '{"goal": "g", "style": "s", "name": "other"}', "it says its name is other, and the file is in-a-rush.json"],
    ["in-a-rush.json", '{"goal": "g", "style": "s", "mood": "x"}', "mood"],
    ["In A Rush.json", "{}", "\"In A Rush\" is not a persona's name"],
  ])("%s refused: %s", (file, text, sentence) => {
    expect(() => personaOf(file, text)).toThrow(DeclarationRefused);
    expect(() => personaOf(file, text)).toThrow(sentence);
  });
});

describe("what the class owns", () => {
  it("is its switches plus the folders beside it, as the declaration sends it", () => {
    class Owns extends Agent {
      static override judges = judges({ on: ["consent", "grounded"] });
      static override personas = personas({ on: ["in-a-hurry"] });
    }
    const dir = folder({ "judges/offers-next-slot.md": OFFERS, "test/personas/in-a-rush.json": RUSH });
    const options = optionsFor(Owns, [], undefined, join(dir, "agent.tsx"), "class Owns {}");
    expect(options.judges).toEqual({ on: ["consent", "grounded"], own: [expect.objectContaining({ name: "offers-next-slot" })] });
    expect(options.personas).toEqual({ on: ["in-a-hurry"], own: [expect.objectContaining({ name: "in-a-rush" })] });
  });

  it("is nothing when the class declares nothing and no folder is there: the org writes them", () => {
    class Silent extends Agent {}
    expect(harnessOf(Silent, join(folder({}), "agent.tsx"))).toEqual({});
    expect(harnessOf(Silent)).toEqual({});
  });

  it("is an empty list plus the switches for a class that declares them with no folder", () => {
    class Bare extends Agent {
      static override judges = judges();
    }
    expect(harnessOf(Bare, join(folder({}), "agent.tsx"))).toEqual({ judges: { on: [], own: [] } });
  });

  it("refuses a folder with files that the class never declared, saying what to write", () => {
    class Silent extends Agent {}
    const withJudges = folder({ "judges/offers-next-slot.md": OFFERS });
    expect(() => harnessOf(Silent, join(withJudges, "agent.tsx"))).toThrow("holds 1 judge(s) and the class declares none: static judges = judges({ on: [\"consent\", …] })");
    const withPersonas = folder({ "test/personas/in-a-rush.json": RUSH });
    expect(() => harnessOf(Silent, join(withPersonas, "agent.tsx"))).toThrow("holds 1 persona(s) and the class declares none: static personas = personas(");
  });
});
