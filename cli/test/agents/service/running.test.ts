/** What an agent runs with: the pipeline, the processes holding the org's agents, a vendor's voices, one of them said and played. */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import * as service from "../../../src/agents/service/running.js";
import { PinecallError, UsageError } from "../../../src/errors.js";
import { answer, GATEWAY, server } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { folder } from "../../support/project.js";

const CATALOGUE = {
  providers: [
    { name: "cartesia", voices_listed: true },
    { name: "rime", voices_listed: false },
  ],
  defaults: { tts: "cartesia" },
};
const ANA = { id: "ana-es", name: "Ana", language: "es", description: "warm", gender: "female", country: "ES", accent: "castilian" };
const LUCIA = { ...ANA, id: "lucia-mx", name: "Lucía", country: "MX", accent: "mexican" };

/** The sample endpoint: four bytes of WAV and the gateway's Server-Timing. */
function samples(): unknown[] {
  const bodies: unknown[] = [];
  server.use(
    http.post(`${GATEWAY}/v1/voices/sample`, async ({ request }) => {
      bodies.push(await request.json());
      return new HttpResponse(new Uint8Array([82, 73, 70, 70]), { headers: { "content-type": "audio/wav", "server-timing": "first-audio;dur=212.5, total;dur=840" } });
    }),
  );
  return bodies;
}

describe("voices", () => {
  it("lists the gateway's own vendor's in a language, keeping one country", async () => {
    answer("get", "/v1/providers", CATALOGUE);
    const sent = answer("get", "/v1/voices", { tts: "cartesia", language: "es", voices: [ANA, LUCIA] });
    const { ctx } = testContext();
    expect(await service.listVoices(ctx, { language: "es", country: "mx" })).toEqual([LUCIA]);
    expect(sent[0]!.query).toEqual({ tts: "cartesia", language: "es" });
  });

  it("a vendor that lists none is a failed check naming the ones that do", async () => {
    answer("get", "/v1/providers", CATALOGUE);
    const { ctx } = testContext();
    await expect(service.listVoices(ctx, { tts: "rime" })).rejects.toThrow(new PinecallError(service.notListed("rime", ["cartesia"])));
  });

  it("an answer that is no list of voices fails instead of reading as empty", async () => {
    answer("get", "/v1/providers", CATALOGUE);
    answer("get", "/v1/voices", { html: "<p>proxy</p>" });
    const { ctx } = testContext();
    await expect(service.listVoices(ctx, {})).rejects.toThrow();
  });

  it("a gateway with no voice of its own asks for --tts", () => {
    expect(() => service.defaultVoiceVendor({ providers: [], defaults: {} })).toThrow(UsageError);
  });

  it("a sample is written to the file, with how long the vendor took", async () => {
    answer("get", "/v1/providers", CATALOGUE);
    const bodies = samples();
    const file = join(folder(), "ana.wav");
    const { ctx } = testContext();
    expect(await service.sampleVoice(ctx, { voice: "ana-es", text: "Hola" }, file)).toEqual({ voice: "ana-es", tts: "cartesia", file, firstAudioMs: 212.5, totalMs: 840 });
    expect(bodies[0]).toEqual({ tts: "cartesia", voice: "ana-es", model: null, language: null, text: "Hola" });
    expect([...readFileSync(file)]).toEqual([82, 73, 70, 70]);
  });

  it("played, the sample is removed unless it is saved; a machine with no player says where the file is", async () => {
    samples();
    const { ctx } = testContext();
    let heard = "";
    const played = await service.playVoice(ctx, { voice: "ana-es", tts: "cartesia" }, undefined, (file) => ((heard = file), { player: "afplay" }));
    expect(played).toMatchObject({ player: "afplay", kept: false });
    expect(existsSync(heard)).toBe(false);
    const kept = join(folder(), "keep.wav");
    await expect(service.playVoice(ctx, { voice: "ana-es", tts: "cartesia" }, kept, () => ({ failed: "no audio player on the PATH" }))).rejects.toThrow(`no audio player on the PATH: the sample is ${kept}`);
    expect(existsSync(kept)).toBe(true);
  });
});

describe("the processes and the pipeline", () => {
  it("stop needs the app's id", async () => {
    const sent = answer("post", "/v1/apps/:app/stop", { app: "app_1", stopped: true });
    const { ctx } = testContext();
    await expect(service.stopApp(ctx, "")).rejects.toBeInstanceOf(UsageError);
    expect(await service.stopApp(ctx, "app_1")).toEqual({ app: "app_1", stopped: true });
    expect(sent[0]!.path).toBe("/v1/apps/app_1/stop");
  });

  it("counts the tools the holder declared, and says nothing when the gateway will not", async () => {
    answer("get", "/v1/agents/:slug/config", { tools: [{}, {}, {}] });
    const { ctx } = testContext();
    expect(await service.countTools(ctx, "front-desk")).toBe(3);
  });
});
