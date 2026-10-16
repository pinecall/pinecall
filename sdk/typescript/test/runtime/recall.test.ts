// Recalled memories as seen by `remembers()` in render().

import { describe, expect, it } from "vitest";

import { wordsRecalled } from "../../src/runtime/recall.js";

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
      tookMs: 12.4,
    },
  ],
  speechId: "s3",
};

describe("the words one memory.ops entry leaves behind", () => {
  it("are every fact's own sentence and the word it was filed under", () => {
    expect(wordsRecalled(RECALLED)).toEqual([
      "su médico habitual es la doctora Vidal",
      "médico habitual",
      "alérgica a la penicilina",
      "alergias",
    ]);
  });

  // `remember` entries are this call's writes, not recalled knowledge.
  it("come from a recall and never from a remember", () => {
    const written = {
      ops: [{ op: "remember" as const, facts: [{ text: "prefiere por la mañana", category: "horario" }], tookMs: 900 }],
    };

    expect(wordsRecalled(written)).toEqual([]);
  });

  it("are none at all when the recall found nothing", () => {
    expect(wordsRecalled({ ops: [{ op: "recall" as const, facts: [], tookMs: 3 }] })).toEqual([]);
  });
});
