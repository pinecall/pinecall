// The captions show whose words the site chose and the visitor left on, the visitor's as they say them and a moment after.

import { describe, expect, it } from "vitest";

import { Hearing, captionsOf, keepVisitorChoice, shows, visitorWantsCaptions, type Heard } from "../../src/tutor/captions.js";

type Turn = Heard["turns"][number];

const said = (text: string, at: number): Turn => ({ role: "user", speech_id: `s${at}`, text });

function logOf(live: string | null, turns: Turn[] = []): Heard {
  return { live: { user: live, agent: null }, turns };
}

function aStorage(): Storage {
  const kept = new Map<string, string>();
  return {
    getItem: (key) => kept.get(key) ?? null,
    setItem: (key, value) => void kept.set(key, value),
    removeItem: (key) => void kept.delete(key),
    clear: () => kept.clear(),
    key: () => null,
    get length() {
      return kept.size;
    },
  };
}

describe("whose words show", () => {
  it("are both sides unless the site names one or none, and none once the visitor turned them off", () => {
    expect(captionsOf(null)).toBe("both");
    expect(captionsOf("caller")).toBe("caller");
    expect(captionsOf("loud")).toBe("both");
    expect(shows("both", true, "caller")).toBe(true);
    expect(shows("agent", true, "caller")).toBe(false);
    expect(shows("none", true, "agent")).toBe(false);
    expect(shows("both", false, "agent")).toBe(false);
  });

  it("keeps the visitor's choice for their next visit, and is on where the browser keeps nothing", () => {
    const storage = aStorage();
    expect(visitorWantsCaptions(() => storage)).toBe(true);
    keepVisitorChoice(() => storage, false);
    expect(visitorWantsCaptions(() => storage)).toBe(false);
    const blocked = (): Storage => {
      throw new Error("SecurityError");
    };
    expect(visitorWantsCaptions(blocked)).toBe(true);
    expect(() => keepVisitorChoice(blocked, false)).not.toThrow();
  });
});

describe("the visitor's words", () => {
  it("are what they are saying, then their finished turn for the linger, then nothing", () => {
    const hearing = new Hearing(2600);
    expect(hearing.at(logOf(null), 0)).toBeNull();
    expect(hearing.at(logOf("show me"), 100)).toBe("show me");
    expect(hearing.at(logOf(null, [said("Show me the pricing.", 1)]), 400)).toBe("Show me the pricing.");
    expect(hearing.at(logOf(null, [said("Show me the pricing.", 1)]), 2900)).toBeNull();
  });

  it("are none of the past on a page that joins a call already under way", () => {
    const hearing = new Hearing(2600);
    expect(hearing.at(logOf(null, [said("Hello.", 1), said("Thanks.", 2)]), 0)).toBeNull();
  });
});
