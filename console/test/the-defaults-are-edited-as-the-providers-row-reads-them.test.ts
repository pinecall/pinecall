/** The Defaults screen writes the providers row as the runtime reads it: stages, fallbacks, prices, voices. */

import { describe, expect, test } from "vitest";

import { withPrice } from "../src/screens/box/defaults-rates";
import { voiceRows } from "../src/screens/box/defaults-voices";
import { fallbacksOf, stageOf, stageSaid } from "../src/screens/box/door-providers";
import { written } from "../src/screens/box/settings-defaults";

describe("a stage as a line", () => {
  test("is vendor/model, or the vendor alone for its plugin's own model", () => {
    expect(stageSaid({ vendor: "google", model: "gemini-3.5-flash-lite" })).toBe("google/gemini-3.5-flash-lite");
    expect(stageSaid({ vendor: "cartesia" })).toBe("cartesia");
  });

  test("splits at the first slash, since a model's id may hold more", () => {
    expect(stageOf("openai/deepdml/faster-whisper")).toEqual({ vendor: "openai", model: "deepdml/faster-whisper" });
    expect(stageOf(" deepgram ")).toEqual({ vendor: "deepgram" });
    expect(stageOf("  ")).toBeNull();
  });

  test("fallbacks are read in the order typed, blanks dropped", () => {
    expect(fallbacksOf("google/gemini-3.5-flash, , anthropic")).toEqual([
      { vendor: "google", model: "gemini-3.5-flash" },
      { vendor: "anthropic" },
    ]);
  });
});

describe("a price typed", () => {
  test("is a number, and an empty field leaves the unit unbilled", () => {
    expect(withPrice({ input: 1, output: 4 }, "input", "0.1")).toEqual({ input: 0.1, output: 4 });
    expect(withPrice({ input: 1, output: 4 }, "output", "")).toEqual({ input: 1 });
  });
});

describe("the voices", () => {
  test("are rows by vendor then language", () => {
    expect(voiceRows({ "cartesia/es": "v1", "cartesia/en": "v2", "elevenlabs/es": "v3" }).map((row) => `${row.vendor}/${row.language}`)).toEqual([
      "cartesia/en",
      "cartesia/es",
      "elevenlabs/es",
    ]);
  });

  test("a voice nobody picked is never written: an empty voice is a silent call", () => {
    const row = { defaults: {}, voices: { "cartesia/es": "v1", "cartesia/pt": "" }, tuning: {}, hints: [], rates: {} };
    expect(written(row).voices).toEqual({ "cartesia/es": "v1" });
  });
});
