// `@agent({ … })`: what a class declares reads on it, a parent's is kept, and the other ways to say it are refused.

import { describe, expect, it } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { agent, declaredOf, refuseStatics, type AgentDeclaration } from "../../src/agent/declaring.js";
import { ownJudge } from "../../src/agent/harness.js";
import { DeclarationRefused } from "../../src/agent/tools.js";

const OFFERS = ownJudge({ name: "offers-a-time", asks: "Did the agent offer a time?" });

describe("what a class declares", () => {
  it("reads on the class, field by field", () => {
    @agent({ language: "es", docs: { base: "clinic", k: 4 }, hold: "off" })
    class Desk extends Agent {}
    expect(declaredOf(Desk, "language")).toBe("es");
    expect(declaredOf(Desk, "docs")).toEqual({ base: "clinic", k: 4 });
    expect(declaredOf(Desk, "hold")).toBe("off");
    expect(declaredOf(Desk, "timezone")).toBeUndefined();
  });

  it("is kept by a class that extends it, which declares over it field by field", () => {
    @agent({ language: "es", timezone: "Europe/Madrid" })
    class Desk extends Agent {}
    @agent({ language: "en" })
    class EnglishDesk extends Desk {}
    class SameDesk extends Desk {}
    expect([declaredOf(EnglishDesk, "language"), declaredOf(EnglishDesk, "timezone")]).toEqual(["en", "Europe/Madrid"]);
    expect(declaredOf(SameDesk, "language")).toBe("es");
    expect(declaredOf(Desk, "language")).toBe("es");
  });

  it("leaves out a field given as undefined", () => {
    @agent({ language: undefined as never, timezone: "Europe/Madrid" })
    class Desk extends Agent {}
    expect(Object.hasOwn(Desk, "language")).toBe(false);
  });

  it("keeps its judges as the two lists the declaration sends: Pinecall's by name, its own whole", () => {
    @agent({ judges: ["consent", OFFERS], personas: ["in-a-hurry"] })
    class Desk extends Agent {}
    const read = Desk as unknown as { judges: unknown; personas: unknown };
    expect(read.judges).toEqual({ on: ["consent"], own: [OFFERS] });
    expect(read.personas).toEqual({ on: ["in-a-hurry"], own: [] });
  });
});

describe("the one way to say it", () => {
  it("refuses a second @agent on one class", () => {
    expect(() => {
      @agent({ language: "es" })
      @agent({ language: "en" })
      class Twice extends Agent {}
      return Twice;
    }).toThrow(new DeclarationRefused("Twice has two @agent({ … }): one says what it is"));
  });

  it("refuses a field no agent declares", () => {
    expect(() => agent({ phone: "+34910000000" } as AgentDeclaration)(class Desk extends Agent {})).toThrow(
      new DeclarationRefused("Desk: @agent({ phone }) is nothing an agent declares"),
    );
  });

  it("refuses a static field that says what the agent is, on the class or on one it extends", () => {
    class ByStatic extends Agent {
      static voice = "cartesia/katie";
    }
    class Below extends ByStatic {}
    const sentence = "ByStatic declares `static voice`: what an agent is goes in @agent({ voice: … }) above the class";
    expect(() => refuseStatics(ByStatic)).toThrow(new DeclarationRefused(sentence));
    expect(() => refuseStatics(Below)).toThrow(new DeclarationRefused(sentence));
  });

  it("lets through a class declared with @agent, a class that declares nothing, and a static of its own", () => {
    @agent({ voice: "cartesia/katie" })
    class Declared extends Agent {
      static readonly OPENS_AT = 9;
    }
    expect(() => refuseStatics(Declared)).not.toThrow();
    expect(() => refuseStatics(class Silent extends Agent {})).not.toThrow();
    expect(() => refuseStatics(Agent)).not.toThrow();
  });
});
