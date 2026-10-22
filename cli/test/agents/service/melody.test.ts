/** The hold melody: read, a file uploaded as it is, the runtime's or none chosen, and the wait set or given back. */

import { writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as service from "../../../src/agents/service/melody.js";
import { UsageError } from "../../../src/errors.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { folder } from "../../support/project.js";

const DOOR = "/v1/agents/:slug/pipeline/hold-audio";
const RUNTIMES = { played: "default", sha256: null, seconds: null, name: null, after_s: 2.5 };

describe("melody", () => {
  it("reads what plays and after how long, for the project's agent", async () => {
    const sent = answer("get", DOOR, RUNTIMES);
    const { ctx } = testContext();
    expect(await service.showMelody(ctx, undefined)).toEqual(RUNTIMES);
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/pipeline/hold-audio");
  });

  it("sends the file's bytes as they are, under its name", async () => {
    const file = join(folder(), "espera.mp3");
    writeFileSync(file, Buffer.from([0x49, 0x44, 0x33, 0, 0, 0]));
    const sent = answer("put", DOOR, { ...RUNTIMES, played: "custom", name: "espera.mp3", seconds: 41.2, sha256: "9f2c" });
    const { ctx } = testContext();
    const held = await service.uploadMelody(ctx, undefined, file);
    expect(held.played).toBe("custom");
    expect(sent[0]!.query).toEqual({ name: "espera.mp3" });
    expect(sent[0]!.body).toBe(6);
  });

  it("a file that is not there is refused before anything is sent", async () => {
    const { ctx } = testContext();
    await expect(service.uploadMelody(ctx, undefined, join(folder(), "none.mp3"))).rejects.toThrow(UsageError);
  });

  it("chooses the runtime's melody or silence", async () => {
    const sent = answer("put", `${DOOR}/played`, { ...RUNTIMES, played: "off" });
    const { ctx } = testContext();
    expect((await service.chooseMelody(ctx, undefined, "off")).played).toBe("off");
    expect(sent[0]!.body).toEqual({ played: "off" });
  });

  it("sets the wait in seconds, and default gives the runtime's back as null", async () => {
    const sent = answer("put", `${DOOR}/after`, ({ body }) => ({ ...RUNTIMES, after_s: (body as { after_s: number | null }).after_s ?? 2.5 }));
    const { ctx } = testContext();
    expect((await service.waitBeforeMelody(ctx, undefined, service.AfterInput.parse("0.8"))).after_s).toBe(0.8);
    expect((await service.waitBeforeMelody(ctx, undefined, service.AfterInput.parse("default"))).after_s).toBe(2.5);
    expect(sent.map((one) => one.body)).toEqual([{ after_s: 0.8 }, { after_s: null }]);
  });

  it("a wait out of range, or no number, is refused in the person's words", () => {
    for (const wrong of ["31", "-1", "soon"]) expect(() => service.AfterInput.parse(wrong)).toThrow(/0 to 30/);
  });
});
