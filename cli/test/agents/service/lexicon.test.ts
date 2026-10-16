/** The lexicon against the gateway: a word said or heard added to the whole row read, guarded like the settings. */

import { describe, expect, it } from "vitest";

import * as service from "../../../src/agents/service/index.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { lexiconRow } from "../../support/fixtures.js";

const LEXICON = { world: "sandbox", yours: null, team: lexiconRow("", 2, [{ word: "Vidal", spoken: "bee-DAHL" }], ["Norte"]), production: null, fixed: [] };

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
