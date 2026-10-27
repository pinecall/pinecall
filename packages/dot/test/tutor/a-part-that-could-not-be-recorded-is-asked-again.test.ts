// A part the door could not record is asked again after a wait, instead of read in silence: a machine that just booted answers a moment later; and one that failed every time is asked again when reached again.

import { afterEach, describe, expect, it, vi } from "vitest";

import { ReadAloud } from "../../src/tutor/aloud.js";
import { readingOf } from "../../src/tutor/reading.js";

afterEach(() => {
  document.body.innerHTML = "";
  vi.useRealTimers();
});

const recorded = (text: string) => ({ say: text, audio: "https://gw/v1/lines/x.mp3", durationMs: 900, words: [], beats: [] });

describe("a part that could not be recorded", () => {
  it("is asked again after a wait, and read once the door answers", async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `<main data-pinecall-read lang="es"><p>Hola.</p></main>`;
    let asked = 0;
    const aloud = new ReadAloud(readingOf(document, "Leer")!, {
      record: async (text) => {
        asked += 1;
        if (asked < 3) throw new Error("400: the tutor has no key yet");
        return recorded(text);
      },
      light: () => undefined,
      press: async () => undefined,
    });

    const voiced = aloud.voice(0);
    await vi.runAllTimersAsync();

    expect(await voiced).toMatchObject({ say: "Hola." });
    expect(asked).toBe(3);
  });

  it("failing every time, is not kept as silent: reached again, it is asked again", async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `<main data-pinecall-read lang="es"><p>Hola.</p></main>`;
    let up = false;
    let asked = 0;
    const aloud = new ReadAloud(readingOf(document, "Leer")!, {
      record: async (text) => {
        asked += 1;
        if (!up) throw new Error("the door is down");
        return recorded(text);
      },
      light: () => undefined,
      press: async () => undefined,
    });

    const first = aloud.voice(0);
    await vi.runAllTimersAsync();
    expect(await first).toBeNull();
    expect(asked).toBe(4);

    up = true;
    const again = aloud.voice(0);
    await vi.runAllTimersAsync();
    expect(await again).toMatchObject({ say: "Hola." });
  });
});
