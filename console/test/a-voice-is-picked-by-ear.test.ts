// Voice picker: countries by count, filters by country, gender and text, and Server-Timing parsing.

import { describe, expect, it } from "vitest";

import { firstAudioIn, type ListedVoice } from "../src/screens/settings/voice-doors";
import { countriesOf, narrowed } from "../src/screens/settings/voice-picker";

function aVoice(name: string, country: string, gender: string, description = ""): ListedVoice {
  return { id: name.toLowerCase(), name, language: "es", description, gender, country, accent: "" };
}

const VOICES = [
  aVoice("Marta", "ES", "feminine", "Approachable, for customer care"),
  aVoice("Marcos", "ES", "masculine", "Calm and measured"),
  aVoice("Mateo", "MX", "masculine", "Warm Mexican host"),
  aVoice("Ximena", "", "feminine"),
];

describe("the countries a picker offers", () => {
  it("are the ones the voices are from, the most voices first, and none for a voice from nowhere", () => {
    expect(countriesOf(VOICES)).toEqual(["ES", "MX"]);
  });
});

describe("narrowing the list", () => {
  it("keeps Spain's voices when Spain is picked", () => {
    expect(narrowed(VOICES, "ES", "any", "").map((one) => one.name)).toEqual(["Marta", "Marcos"]);
  });

  it("keeps one gender, and a word of the name or the manner, whatever its case", () => {
    expect(narrowed(VOICES, "", "masculine", "").map((one) => one.name)).toEqual(["Marcos", "Mateo"]);
    expect(narrowed(VOICES, "", "any", "CUSTOMER").map((one) => one.name)).toEqual(["Marta"]);
  });
});

describe("the vendor's wait", () => {
  it("is read off Server-Timing, and is nothing when the gateway sent none", () => {
    expect(firstAudioIn("first-audio;dur=271, total;dur=955")).toBe(271);
    expect(firstAudioIn("total;dur=955")).toBeNull();
  });
});
