/** The lexicon against the gateway: a word said or heard added to the whole row read, guarded like the settings. */

import { describe, expect, it } from "vitest";

import * as render from "../../../src/agents/render.js";
import * as service from "../../../src/agents/service/index.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { lexiconRow } from "../../support/fixtures.js";

const LEXICON = { world: "sandbox" as const, yours: null, team: lexiconRow("", 2, [{ word: "Vidal", spoken: "bee-DAHL" }], ["Norte"]), production: null, fixed: [] };

describe("the lexicon", () => {
  it("a word said joins the team's words, guarded by the person's empty corner", async () => {
    answer("get", "/v1/agents/:slug/lexicon", LEXICON);
    const sent = answer("put", "/v1/agents/:slug/lexicon", LEXICON);
    const { ctx } = testContext();
    await service.sayWord(ctx, service.SayWordInput.parse({ word: "Ruiz", say: "roo-EETH" }));
    expect(sent[0]!.body).toEqual({
      lexicon: { said: [{ word: "Vidal", spoken: "bee-DAHL" }, { word: "Ruiz", spoken: "roo-EETH" }], heard: ["Norte"] },
      if_version: 0,
      note: null,
      team: false,
    });
  });

  it("a word heard twice is kept once", async () => {
    answer("get", "/v1/agents/:slug/lexicon", LEXICON);
    const sent = answer("put", "/v1/agents/:slug/lexicon", LEXICON);
    const { ctx } = testContext();
    await service.hearWords(ctx, service.WordsInput.parse({ words: ["Norte", "Clínica"], team: true }));
    expect(sent[0]!.body).toMatchObject({ lexicon: { heard: ["Norte", "Clínica"] }, if_version: 2, team: true });
  });

  it("rm takes a word out of both lists", async () => {
    answer("get", "/v1/agents/:slug/lexicon", { ...LEXICON, team: lexiconRow("", 2, [{ word: "Norte", spoken: "NOR-teh" }], ["Norte", "Vidal"]) });
    const sent = answer("put", "/v1/agents/:slug/lexicon", LEXICON);
    const { ctx } = testContext();
    await service.removeWords(ctx, service.WordsInput.parse({ words: ["Norte"] }));
    expect((sent[0]!.body as { lexicon: unknown }).lexicon).toEqual({ said: [], heard: ["Vidal"] });
  });

  it("starts from nothing when no corner set a word", async () => {
    answer("get", "/v1/agents/:slug/lexicon", { ...LEXICON, team: null });
    const sent = answer("put", "/v1/agents/:slug/lexicon", LEXICON);
    const { ctx } = testContext();
    await service.hearWords(ctx, service.WordsInput.parse({ words: ["Norte"] }));
    expect((sent[0]!.body as { lexicon: unknown }).lexicon).toEqual({ said: [], heard: ["Norte"] });
  });
});

// T F8: a write with --team answered "your corner" and showed the person's own words.
describe("the lexicon shown after a write", () => {
  const both = { ...LEXICON, yours: lexiconRow("ana@clinica.test", 1, [{ word: "DKV", spoken: "de ka uve" }], []) };

  it("with --team is the team's corner it wrote", () => {
    const lines = render.lexicon(both, "team");
    expect(lines[0]).toBe("lexicon · sandbox · the team's corner");
    expect(lines[1]).toBe('  said     Vidal → "bee-DAHL"');
  });

  it("without it is the person's own corner", () => {
    const lines = render.lexicon(both);
    expect(lines[0]).toBe("lexicon · sandbox · your corner");
    expect(lines[1]).toBe('  said     DKV → "de ka uve"');
  });
});
