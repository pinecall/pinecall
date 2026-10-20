/** A run's played_by carries only the words a person chose; nothing chosen sends nothing, and the persona plays as written. */

import { expect, test } from "vitest";

import { playedBy } from "../src/screens/simulations/simulating";

test("nothing chosen sends no played_by", () => {
  expect(playedBy({ llm: "", tts: "", voice: "" })).toEqual({});
});

test("a voice vendor and a voice are sent alone, the model left to the persona", () => {
  expect(playedBy({ llm: "", tts: "google", voice: "Puck" })).toEqual({ played_by: { tts: "google", voice: "Puck" } });
});
