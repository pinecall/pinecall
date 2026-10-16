/** Each lookup renders as one line, with its results beneath. */

import { expect, test } from "vitest";

import { factLines, memoryLine, sourceLines, sourcesLine } from "../src/lib/lookups";

const RECALLED = {
  ops: [
    {
      op: "recall" as const,
      contact: "+34600000001",
      query: "quiero cita con la doctora Vidal",
      facts: [
        { id: "f1", text: "su médico habitual es la doctora Vidal", category: "médico habitual", score: 0.9 },
        { id: "f2", text: "alérgica a la penicilina", category: "alergias", score: 0.4 },
      ],
      took_ms: 12.4,
    },
  ],
  speech_id: "s3",
};

const RETRIEVED = {
  query: "qué cubre DKV",
  sources: [
    { id: "c1", path: "seguros-y-autorizaciones.md", heading: "DKV", score: 0.0328, excerpt: "Con autorización previa." },
    { id: "c2", path: "preparacion-de-pruebas.md", heading: null, score: 0.0161 },
  ],
  took_ms: 41.2,
};

test("a recall reads as the op, how many facts, and how long", () => {
  expect(memoryLine(RECALLED)).toBe("recall · 2 facts · 12 ms");
  expect(factLines(RECALLED)).toEqual([
    "su médico habitual es la doctora Vidal (médico habitual)",
    "alérgica a la penicilina (alergias)",
  ]);
});

test("a retrieval reads as how many sources and how long, each source by where it came from", () => {
  expect(sourcesLine(RETRIEVED)).toBe("2 sources · 41 ms");
  expect(sourceLines(RETRIEVED)).toEqual([
    "seguros-y-autorizaciones.md › DKV · 0.033",
    "preparacion-de-pruebas.md · 0.016",
  ]);
});

test("an entry with several ops reads them one after the other", () => {
  const two = { ops: [RECALLED.ops[0]!, { op: "remember" as const, facts: [], took_ms: 2100 }] };
  expect(memoryLine(two)).toBe("recall · 2 facts · 12 ms; remember · 0 facts · 2100 ms");
});
