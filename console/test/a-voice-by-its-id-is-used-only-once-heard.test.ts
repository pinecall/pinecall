// A voice no list carries is named by its id, and `Use` takes it only once the vendor said a line with it.

import { describe, expect, it } from "vitest";

import { usable } from "../src/screens/settings/voice-by-id";

describe("a voice by its id", () => {
  it("is usable once the vendor has said a line with exactly that id", () => {
    expect(usable("v-mine", "v-mine", "")).toBe(true);
    expect(usable("  v-mine  ", "v-mine", "")).toBe(true);
  });

  it("is not usable before it was heard, or after the id changed", () => {
    expect(usable("v-mine", null, "")).toBe(false);
    expect(usable("v-mine-2", "v-mine", "")).toBe(false);
    expect(usable("", null, "")).toBe(false);
  });

  it("is not offered again when it is the voice already in use", () => {
    expect(usable("v-mine", "v-mine", "v-mine")).toBe(false);
  });
});
