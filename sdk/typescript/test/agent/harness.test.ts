// The judges and the personas a class owns: each built by sentence or refused by one, and the class's `own` sent as declared.

import { describe, expect, it } from "vitest";

import { Agent, DeclarationRefused, judges, optionsFor, ownJudge, ownPersona, personas } from "../../src/index.js";
import { harnessOf } from "../../src/agent/harness.js";

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
  it("is its switches plus its own, as the declaration sends it", () => {
    class Owns extends Agent {
      static override judges = judges({ on: ["consent", "grounded"], own: [OFFERS] });
      static override personas = personas({ on: ["in-a-hurry"], own: [RUSH] });
    }
    const options = optionsFor(Owns, [], undefined, undefined, "class Owns {}");
    expect(options.judges).toEqual({ on: ["consent", "grounded"], own: [OFFERS] });
    expect(options.personas).toEqual({ on: ["in-a-hurry"], own: [RUSH] });
  });

  it("is nothing when the class declares neither: the org writes them", () => {
    class Silent extends Agent {}
    expect(harnessOf(Silent)).toEqual({});
  });

  it("is an empty list plus the switches for a class that declares them with none of its own", () => {
    class Bare extends Agent {
      static override judges = judges();
    }
    expect(harnessOf(Bare)).toEqual({ judges: { on: [], own: [] } });
  });

  it("refuses two of the same name, and an own judge written as a plain object that is wrong", () => {
    expect(() => judges({ own: [OFFERS, OFFERS] })).toThrow("two judges called offers-next-slot: a name is declared once");
    expect(() => personas({ own: [RUSH, { ...RUSH }] })).toThrow("two personas called in-a-rush: a name is declared once");
    expect(() => judges({ own: [{ ...OFFERS, answer: "maybe" as never }] })).toThrow('offers-next-slot: answer is "maybe", not one of verdict, choice, score');
  });
});
