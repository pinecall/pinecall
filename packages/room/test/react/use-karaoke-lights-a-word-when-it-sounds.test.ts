// useKaraoke splits the reply where the voice is, moving on with the clock, and lets go when the turn closes.

import { type Entry } from "../../src/wire/envelope.js";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useKaraoke } from "../../src/react/index.js";

Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);

const word = (seq: number, text: string, start: number): Entry => ({
  seq, ts: seq, call: "call_x", agent: "bernardo", type: "agent.transcript", ephemeral: true,
  data: { speech_id: "sp_2", text, final: false, start, end: start + 0.3 },
});

describe("useKaraoke", () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "performance"] }));
  afterEach(() => vi.useRealTimers());

  it("lights each word at its second, and returns nothing once the turn has closed", () => {
    const seen: (string | null)[] = [];
    const Reply = ({ entries }: { entries: Entry[] }): null => {
      const split = useKaraoke(entries);
      seen.push(split === null ? null : `${split.lit}|${split.coming}`);
      return null;
    };
    const saying = [word(1, "Two ", 0), word(2, "or ", 0.4), word(3, "four? ", 0.7)];
    const root = createRoot(document.createElement("div"));
    act(() => root.render(createElement(Reply, { entries: saying })));
    expect(seen.at(-1)).toBe("Two |or four? ");
    act(() => vi.advanceTimersByTime(500));
    expect(seen.at(-1)).toBe("Two or |four? ");
    act(() => vi.advanceTimersByTime(500));
    expect(seen.at(-1)).toBe("Two or four? |");
    const closed: Entry = {
      seq: 4, ts: 4, call: "call_x", agent: "bernardo", type: "turn.agent", ephemeral: false,
      data: { speech_id: "sp_2", text: "Two or four?", interrupted: false, metrics: {} },
    };
    act(() => root.render(createElement(Reply, { entries: [...saying, closed] })));
    expect(seen.at(-1)).toBeNull();
    act(() => root.unmount());
  });
});
