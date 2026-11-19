// The judges a class owns and the callers its test folder holds: each built by sentence or refused by one, and sent as declared.

import { describe, expect, it } from "vitest";

import { Agent, DeclarationRefused, agent, optionsFor, ownJudge, ownPersona } from "../../src/index.js";
import { CALLERS_MOVED, harnessOf, judges, namesItsCallers, personas, rosterIn, testedWith } from "../../src/agent/harness.js";

const OFFERS = ownJudge({ name: "offers-next-slot", asks: "Did the agent offer the next free slot before the caller asked twice?", reads: ["facts"] });

const RUSH = ownPersona({ name: "in-a-rush", goal: "book today", style: "short, interrupts", expects: ["The agent should offer today."], behavior: { interrupts: 0.3, pauseS: 1 } });

describe("a judge of the agent's own", () => {
  it("is the question it asks, with how and when it answers filled in", () => {
    expect(OFFERS).toEqual({
      name: "offers-next-slot",
      question: "Did the agent offer the next free slot before the caller asked twice?",
      answer: "verdict",
      choices: [],
      when: "always",
      trigger: "",
      reads: ["facts"],
    });
  });

  it("answers one of several, on a trigger, reading what it was told to", () => {
    const read = ownJudge({ name: "reason", asks: "Why did they call?", answer: "choice", choices: ["book", "cancel"], when: "trigger", trigger: "Did the caller say why?", reads: ["prompt", "evidence"] });
    expect([read.answer, read.choices, read.when, read.trigger, read.reads]).toEqual(["choice", ["book", "cancel"], "trigger", "Did the caller say why?", ["prompt", "evidence"]]);
  });

  it.each([
    [{ name: "offers", asks: " " }, "offers: a judge asks a question of a call: write it as asks"],
    [{ name: "offers", asks: "Q?", answer: "maybe" }, 'offers: answer is "maybe", not one of verdict, choice, score'],
    [{ name: "offers", asks: "Q?", answer: "choice", choices: ["a"] }, "offers: a judge that answers one of several needs at least two choices"],
    [{ name: "offers", asks: "Q?", choices: ["a", "b"] }, "offers: only a judge that answers one of several takes choices"],
    [{ name: "offers", asks: "Q?", when: "trigger" }, "offers: a judge that runs on a trigger needs the trigger's question"],
    [{ name: "offers", asks: "Q?", reads: ["dreams"] }, 'offers: reads is "dreams", not one of prompt, evidence, facts'],
    [{ name: "Offers Slot", asks: "Q?" }, "\"Offers Slot\" is not a judge's name: lower-case words joined by hyphens"],
  ])("%o is refused: %s", (input, sentence) => {
    expect(() => ownJudge(input as never)).toThrow(DeclarationRefused);
    expect(() => ownJudge(input as never)).toThrow(sentence);
  });
});

describe("a persona of the agent's own", () => {
  it("is what a PUT takes, under its name, with the wire's keys camelCased for the class", () => {
    expect(RUSH).toEqual({
      name: "in-a-rush",
      goal: "book today",
      style: "short, interrupts",
      expects: ["The agent should offer today."],
      behavior: { interrupts: 0.3, pauseS: 1 },
    });
  });

  it.each([
    [{ name: "in-a-rush", style: "s" }, "in-a-rush: a persona wants something: write its goal, in the first person"],
    [{ name: "in-a-rush", goal: "g" }, "in-a-rush: a persona talks some way: write its style"],
    [{ name: "in-a-rush", goal: "g", style: "s", mood: "x" }, "in-a-rush: it: Unrecognized key"],
    [{ name: "In A Rush", goal: "g", style: "s" }, "\"In A Rush\" is not a persona's name"],
  ])("%o is refused: %s", (input, sentence) => {
    expect(() => ownPersona(input as never)).toThrow(DeclarationRefused);
    expect(() => ownPersona(input as never)).toThrow(sentence);
  });
});

describe("what the class owns", () => {
  it("is a list, Pinecall's by their name and its own whole, sent as the two lists the declaration carries", () => {
    @agent({ judges: ["consent", OFFERS, "grounded"], personas: ["in-a-hurry", RUSH] })
    class Owns extends Agent {}
    const options = optionsFor(Owns, [], undefined, undefined, "class Owns {}");
    expect(options.judges).toEqual({ on: ["consent", "grounded"], own: [OFFERS] });
    expect(options.personas).toEqual({ on: ["in-a-hurry"], own: [RUSH] });
  });

  it("is nothing when the class declares neither: the org writes them", () => {
    class Silent extends Agent {}
    expect(harnessOf(Silent)).toEqual({});
  });

  it("is an empty list plus the switches for a class that declares them with none of its own", () => {
    @agent({ judges: [] })
    class Bare extends Agent {}
    expect(harnessOf(Bare)).toEqual({ judges: { on: [], own: [] } });
  });

  it("refuses a list that is no list, by its sentence", () => {
    expect(() => agent({ judges: "consent" as never })(class Wrong extends Agent {})).toThrow("judges is a list: a name for one of Pinecall's, an object for one of your own");
  });

  it("refuses two of the same name, and an own judge written as a plain object that is wrong", () => {
    expect(() => judges({ own: [OFFERS, OFFERS] })).toThrow("two judges called offers-next-slot: a name is declared once");
    expect(() => personas({ own: [RUSH, { ...RUSH }] })).toThrow("two personas called in-a-rush: a name is declared once");
    expect(() => judges({ own: [{ ...OFFERS, answer: "maybe" as never }] })).toThrow('offers-next-slot: answer is "maybe", not one of verdict, choice, score');
  });
});

describe("the callers a test folder holds", () => {
  const FILE = "agents/front-desk/test/personas.ts";

  it("are every ownPersona the file exports, with Pinecall's it names in on; whatever else it exports is no caller", () => {
    const rush = ownPersona(RUSH);
    expect(rosterIn({ on: ["in-a-hurry"], rush, NOTE: "a line", plain: { ...RUSH, name: "plain" } }, FILE)).toEqual({ on: ["in-a-hurry"], own: [RUSH] });
    expect(rosterIn({}, FILE)).toEqual({ on: [], own: [] });
  });

  it("refuse an on that is no list of names, and two of one name", () => {
    expect(() => rosterIn({ on: "in-a-hurry" }, FILE)).toThrow(`${FILE}: on is the names of Pinecall's callers the agent is tested with, a list of strings`);
    expect(() => rosterIn({ on: [1] }, FILE)).toThrow(DeclarationRefused);
    expect(() => rosterIn({ one: ownPersona(RUSH), two: ownPersona(RUSH) }, FILE)).toThrow("two personas called in-a-rush: a name is declared once");
  });

  it("are what the declaration sends for the class they are read beside", () => {
    @agent({ judges: ["consent"] })
    class Tested extends Agent {}
    testedWith(Tested, rosterIn({ on: ["in-a-hurry"], rush: ownPersona(RUSH) }, FILE), FILE);
    expect(namesItsCallers(Tested)).toBe(false);
    expect(harnessOf(Tested)).toEqual({ judges: { on: ["consent"], own: [] }, personas: { on: ["in-a-hurry"], own: [RUSH] } });
  });

  it("still play from a class that names them and has no file, which is told where they moved", () => {
    @agent({ personas: ["in-a-hurry", RUSH] })
    class Names extends Agent {}
    expect(namesItsCallers(Names)).toBe(true);
    expect(harnessOf(Names).personas).toEqual({ on: ["in-a-hurry"], own: [RUSH] });
    expect(CALLERS_MOVED).toContain("their place is now test/personas.ts beside the goldens");
  });

  it("are refused beside a class that names them too", () => {
    @agent({ personas: ["in-a-hurry"] })
    class Both extends Agent {}
    expect(() => testedWith(Both, { on: [], own: [] }, FILE)).toThrow(`Both declares personas in @agent({ … }) and ${FILE} holds them too: the file is their place — take personas out of the class`);
  });
});
