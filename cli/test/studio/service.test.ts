/** Studio against the gateway: made, pulled to a file and pushed over the release read, a 409 said, arguments read, a deploy, the code saved or written out. */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import { GatewayError, UsageError } from "../../src/errors.js";
import * as service from "../../src/studio/service.js";
import { testContext } from "../support/context.js";
import { answer, GATEWAY, refuse, server } from "../support/gateway.js";
import { folder, write } from "../support/project.js";
import { zipOf } from "../support/zip.js";

const DEFINITION = {
  instructions: "You answer the phone for Clínica Norte.",
  greeting: { say: "Clínica Norte, good morning.", reply: null },
  tools: [{ name: "find_slot", description: "free slots on a day", method: "GET", url: "https://api.clinica.test/slots", headers: [], params: [{ name: "day", type: "string", description: "the day", required: true }], announce: null, timeout_s: 10 }],
  collect: null,
};
const AN_AGENT = { name: "front-desk", env: "sandbox", release: 3, definition: DEFINITION, author: "ana@clinica.test", note: "", saved_at: 1_792_150_000, stopped: false };

describe("an agent", () => {
  it("is made with its name and note, and the gateway's template without a definition", async () => {
    const sent = answer("post", "/v1/studio/agents", { ...AN_AGENT, release: 1 });
    const { ctx } = testContext();
    expect((await service.createAgent(ctx, "front-desk", "first")).release).toBe(1);
    expect(sent[0]!.body).toEqual({ name: "front-desk", note: "first" });
    expect(sent[0]!.env).toBe("sandbox");
  });

  it("is saved over the release it was read at", async () => {
    const sent = answer("put", "/v1/studio/agents/:name", { ...AN_AGENT, release: 4 });
    const { ctx } = testContext();
    expect((await service.saveAgent(ctx, "front-desk", DEFINITION as service.DefinitionInput, 3, "")).release).toBe(4);
    expect(sent[0]!.path).toBe("/v1/studio/agents/front-desk");
    expect(sent[0]!.body).toEqual({ definition: DEFINITION, based_on: 3, note: "" });
  });
});

describe("a pulled file", () => {
  it("holds the release beside the definition, at <name>.studio.json unless told", async () => {
    answer("get", "/v1/studio/agents/:name", AN_AGENT);
    const root = folder();
    const { ctx } = testContext({ cwd: root });
    expect(await service.pullAgent(ctx, "front-desk")).toEqual({ name: "front-desk", release: 3, file: "front-desk.studio.json" });
    expect(JSON.parse(readFileSync(join(root, "front-desk.studio.json"), "utf8"))).toEqual({ release: 3, definition: DEFINITION });
  });

  it("is pushed based on its release, and then stands at the release saved", async () => {
    const sent = answer("put", "/v1/studio/agents/:name", { ...AN_AGENT, release: 4 });
    const root = folder();
    write(root, "desk.json", JSON.stringify({ release: 3, definition: DEFINITION }));
    const { ctx } = testContext({ cwd: root });
    const pushed = await service.pushAgent(ctx, "front-desk", "desk.json", "books the visit");
    expect([pushed.agent.release, pushed.basedOn, pushed.file]).toEqual([4, 3, "desk.json"]);
    expect(sent[0]!.body).toEqual({ definition: DEFINITION, based_on: 3, note: "books the visit" });
    expect((JSON.parse(readFileSync(join(root, "desk.json"), "utf8")) as { release: number }).release).toBe(4);
  });

  it("refused with a 409 says to pull again, and is left as it was", async () => {
    refuse("put", "/v1/studio/agents/:name", 409, "this agent is at release 5 now, not the one you read: read it again, then save");
    const root = folder();
    write(root, "front-desk.studio.json", JSON.stringify({ release: 3, definition: DEFINITION }));
    const { ctx } = testContext({ cwd: root });
    const failed = await service.pushAgent(ctx, "front-desk", undefined, "").catch((error: unknown) => error);
    expect(failed).toBeInstanceOf(GatewayError);
    expect((failed as GatewayError).status).toBe(409);
    expect((failed as GatewayError).message).toContain("`pinecall studio pull front-desk` writes it again");
    expect((JSON.parse(readFileSync(join(root, "front-desk.studio.json"), "utf8")) as { release: number }).release).toBe(3);
  });

  it("that is not what pull writes is refused before anything is sent, naming the field", async () => {
    const root = folder();
    write(root, "front-desk.studio.json", JSON.stringify({ release: 3, definition: { ...DEFINITION, instruction: "typo" } }));
    const { ctx } = testContext({ cwd: root });
    await expect(service.pushAgent(ctx, "front-desk", undefined, "")).rejects.toThrow(UsageError);
    await expect(service.pushAgent(ctx, "front-desk", undefined, "")).rejects.toThrow(/definition/);
  });
});

describe("a tool's arguments", () => {
  it("read a number or true/false as one, and anything else as text", () => {
    expect(service.toolArguments(["day=2026-10-21", "people=2", "price=12.5", "urgent=true", "phone=+59899123456", "code=007", "note=a=b"])).toEqual({
      day: "2026-10-21",
      people: 2,
      price: 12.5,
      urgent: true,
      phone: "+59899123456",
      code: "007",
      note: "a=b",
    });
    expect(() => service.toolArguments(["day"])).toThrow(service.NOT_A_PAIR("day"));
  });

  it("are sent with the tool's name, and what came back is answered", async () => {
    const sent = answer("post", "/v1/studio/agents/:name/try", { status: 200, body: { free: 2 }, error: null, duration_ms: 184 });
    const { ctx } = testContext();
    expect(await service.tryTool(ctx, "front-desk", "find_slot", { day: "2026-10-21" })).toEqual({ status: 200, body: { free: 2 }, error: null, duration_ms: 184 });
    expect(sent[0]!.body).toEqual({ tool: "find_slot", arguments: { day: "2026-10-21" } });
  });
});

describe("a deploy", () => {
  it("names the sandbox's release when given, and refuses one that is no number", async () => {
    const sent = answer("post", "/v1/studio/agents/:name/deploy", { ...AN_AGENT, env: "production", release: 1 });
    const { ctx } = testContext();
    await expect(service.deployAgent(ctx, "front-desk", 0, "")).rejects.toBeInstanceOf(UsageError);
    expect((await service.deployAgent(ctx, "front-desk", 3, "first week")).env).toBe("production");
    expect(sent[0]!.body).toEqual({ release: 3, note: "first week" });
    expect(sent[0]!.env).toBe("sandbox");
  });
});

describe("the code", () => {
  const ZIP = zipOf({ "front-desk/package.json": '{"name":"front-desk"}', "front-desk/agents/front-desk/agent.tsx": "export default class {}\n" });
  const served = (): void => {
    server.use(http.get(`${GATEWAY}/v1/studio/agents/:name/code`, () => new HttpResponse(ZIP, { headers: { "content-type": "application/zip" } })));
  };

  it("is saved as <name>.zip", async () => {
    served();
    const root = folder();
    const { ctx } = testContext({ cwd: root });
    expect(await service.downloadCode(ctx, "front-desk")).toEqual({ name: "front-desk", file: "front-desk.zip", folder: null, bytes: ZIP.length, files: 0 });
    expect(readFileSync(join(root, "front-desk.zip")).equals(ZIP)).toBe(true);
  });

  it("with --out is written there, the project under the agent's name", async () => {
    served();
    const root = folder();
    const { ctx } = testContext({ cwd: root });
    expect(await service.downloadCode(ctx, "front-desk", "out")).toMatchObject({ folder: join("out", "front-desk"), files: 2 });
    expect(readFileSync(join(root, "out/front-desk/agents/front-desk/agent.tsx"), "utf8")).toBe("export default class {}\n");
    expect(existsSync(join(root, "front-desk.zip"))).toBe(false);
  });

  it("is written over no file that is there already", async () => {
    served();
    const root = folder();
    write(root, "out/front-desk/package.json", "mine");
    const { ctx } = testContext({ cwd: root });
    await expect(service.downloadCode(ctx, "front-desk", "out")).rejects.toThrow(service.ALREADY_THERE(join("out", "front-desk/package.json")));
    expect(readFileSync(join(root, "out/front-desk/package.json"), "utf8")).toBe("mine");
  });
});
