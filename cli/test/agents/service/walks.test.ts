/** A tutor's walks: listed as the agent published them, none while it published none, and one played here a sentence at a time. */

import { describe, expect, it } from "vitest";

import * as service from "../../../src/agents/service/walks.js";
import { PinecallError } from "../../../src/errors.js";
import { answer, refuse } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";

const DOOR = "/v1/agents/:slug/public/walks";
const TOUR = {
  name: "tour",
  title: "Site tour",
  voice: "cartesia sonic-3",
  steps: [
    { say: "Up here are our services.", audio: "https://gw.example/v1/lines/a.mp3", durationMs: 1600, words: [], beats: [] },
    { say: "That is all.", audio: "https://gw.example/v1/lines/b.mp3", durationMs: 900, words: [], beats: [] },
  ],
};

describe("walks", () => {
  it("lists what the project's agent published in this env, each with its sentences, length and voice", async () => {
    const sent = answer("get", DOOR, { walks: [TOUR, { name: "broken", steps: [] }] });
    const { ctx } = testContext();

    expect(await service.listWalks(ctx, undefined)).toEqual({
      agent: "front-desk",
      walks: [{ name: "tour", title: "Site tour", sentences: 2, ms: 2500, voice: "cartesia sonic-3" }],
    });
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/public/walks");
    expect(sent[0]!.query).toEqual({ env: "sandbox" });
  });

  it("lists none while the agent published none", async () => {
    refuse("get", DOOR, 404, "agent front-desk published no document walks in sandbox");
    const { ctx } = testContext();

    expect((await service.listWalks(ctx, undefined)).walks).toEqual([]);
  });

  it("plays a walk named by its title, saying each sentence as its audio starts, and keeps no file", async () => {
    answer("get", DOOR, { walks: [TOUR] });
    const fetched = answer("get", "/v1/lines/:line", { audio: true });
    const { ctx } = testContext();
    const said: string[] = [];
    const files: string[] = [];

    const played = await service.playWalk(ctx, undefined, "site tour", (file) => (files.push(file), { player: "afplay" }), (sentence) => said.push(sentence));

    expect(played).toEqual({ walk: "tour", sentences: 2, player: "afplay" });
    expect(said).toEqual(["Up here are our services.", "That is all."]);
    expect(fetched.map((one) => one.path)).toEqual(["/v1/lines/a.mp3", "/v1/lines/b.mp3"]);
    expect(files.map((file) => file.endsWith(".mp3"))).toEqual([true, true]);
  });

  it("names the walks there are when the one asked for is not one of them", async () => {
    answer("get", DOOR, { walks: [TOUR] });
    const { ctx } = testContext();

    await expect(service.playWalk(ctx, undefined, "pricing", () => ({ player: "afplay" }), () => undefined)).rejects.toThrow(new PinecallError("no walk pricing: there are tour"));
  });
});
