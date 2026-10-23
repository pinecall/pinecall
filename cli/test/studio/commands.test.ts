/** `pinecall studio` as typed: the agents as a table, one made, pulled and pushed, a tool tried, a deploy, the code saved. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import { answer, GATEWAY, refuse, server } from "../support/gateway.js";
import { folder, write } from "../support/project.js";
import { run, runJson } from "../support/run.js";
import { zipOf } from "../support/zip.js";

const DEFINITION = { instructions: "You answer the phone for Clínica Norte.", greeting: null, tools: [], collect: null };
const AN_AGENT = { name: "front-desk", env: "sandbox", release: 3, definition: DEFINITION, author: "ana@clinica.test", note: "", saved_at: 1_792_150_000, stopped: false };

describe("pinecall studio", () => {
  it("alone lists the org's Studio agents: release, who saved it, stopped", async () => {
    answer("get", "/v1/studio/agents", { agents: [AN_AGENT, { ...AN_AGENT, name: "sales", release: 12, author: "luis@clinica.test", stopped: true }] });
    const ran = await run(["studio"]);
    expect(ran.code).toBe(0);
    expect(ran.out).toBe(
      ["NAME        RELEASE  SAVED BY           STOPPED", "front-desk  3        ana@clinica.test   no", "sales       12       luis@clinica.test  yes", ""].join("\n"),
    );
  });

  it("list says how to make one when there is none", async () => {
    answer("get", "/v1/studio/agents", { agents: [] });
    expect((await run(["studio", "list"])).out).toContain("`pinecall studio new <name>` makes one");
  });

  it("new makes one in the env asked", async () => {
    const sent = answer("post", "/v1/studio/agents", { ...AN_AGENT, release: 1 });
    const ran = await run(["studio", "new", "front-desk"]);
    expect(ran.out).toBe("front-desk: made in the sandbox as release 1 — `pinecall studio pull front-desk` writes it to a file\n");
    expect(sent[0]!.body).toEqual({ name: "front-desk", note: "" });
  });

  it("pull writes the file, and push saves it over the release pulled", async () => {
    answer("get", "/v1/studio/agents/:name", AN_AGENT);
    const saved = answer("put", "/v1/studio/agents/:name", { ...AN_AGENT, release: 4 });
    const root = folder();
    expect((await run(["studio", "pull", "front-desk"], { cwd: root })).out).toBe("front-desk: release 3 written to front-desk.studio.json\n");
    const ran = await run(["studio", "push", "front-desk", "--note", "books the visit"], { cwd: root });
    expect(ran.out).toBe("front-desk: front-desk.studio.json saved as release 4 in the sandbox\n");
    expect(saved[0]!.body).toEqual({ definition: DEFINITION, based_on: 3, note: "books the visit" });
  });

  it("push of a file nothing changed in says so", async () => {
    answer("put", "/v1/studio/agents/:name", AN_AGENT);
    const root = folder();
    write(root, "desk.json", JSON.stringify({ release: 3, definition: DEFINITION }));
    expect((await run(["studio", "push", "front-desk", "--file", "desk.json"], { cwd: root })).out).toBe("front-desk: nothing in desk.json changed — still release 3\n");
  });

  it("push refused with a 409 exits 2 and says to pull again", async () => {
    refuse("put", "/v1/studio/agents/:name", 409, "this agent is at release 5 now, not the one you read: read it again, then save");
    const root = folder();
    write(root, "front-desk.studio.json", JSON.stringify({ release: 3, definition: DEFINITION }));
    const ran = await run(["studio", "push", "front-desk"], { cwd: root });
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("`pinecall studio pull front-desk` writes it again");
  });

  it("push without the file is refused naming it", async () => {
    const ran = await run(["studio", "push", "front-desk"], { cwd: folder() });
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("front-desk.studio.json");
  });

  it("try sends the arguments read, and prints status, time and body", async () => {
    const sent = answer("post", "/v1/studio/agents/:name/try", { status: 200, body: { free: 2 }, error: null, duration_ms: 184 });
    const ran = await run(["studio", "try", "front-desk", "find_slot", "day=2026-10-21", "people=2"]);
    expect(ran.out).toBe('200 · 184 ms\n{\n  "free": 2\n}\n');
    expect(sent[0]!.body).toEqual({ tool: "find_slot", arguments: { day: "2026-10-21", people: 2 } });
  });

  it("try prints what went wrong when the request never answered", async () => {
    answer("post", "/v1/studio/agents/:name/try", { status: null, body: null, error: "timed out after 10s", duration_ms: 10_000 });
    expect((await run(["studio", "try", "front-desk", "find_slot"])).out).toBe("no answer · 10000 ms\ntimed out after 10s\n");
  });

  it("try refuses a word that is not key=value", async () => {
    expect((await run(["studio", "try", "front-desk", "find_slot", "tomorrow"])).code).toBe(2);
  });

  it("deploy puts the sandbox's release in production, asked in the sandbox", async () => {
    const sent = answer("post", "/v1/studio/agents/:name/deploy", { ...AN_AGENT, env: "production", release: 1 });
    const ran = await run(["studio", "deploy", "front-desk", "--release", "3"]);
    expect(ran.out).toBe("front-desk: in production as release 1, answering from its next call\n");
    expect(sent[0]!.body).toEqual({ release: 3, note: "" });
    expect(sent[0]!.env).toBe("sandbox");
  });

  it("deploy refuses a release that is no number", async () => {
    expect((await run(["studio", "deploy", "front-desk", "--release", "latest"])).code).toBe(2);
  });

  it("code saves the zip as <name>.zip", async () => {
    const zip = zipOf({ "front-desk/package.json": "{}" });
    server.use(http.get(`${GATEWAY}/v1/studio/agents/:name/code`, () => new HttpResponse(zip, { headers: { "content-type": "application/zip" } })));
    const root = folder();
    const ran = await run(["studio", "code", "front-desk"], { cwd: root });
    expect(ran.out).toMatch(/^front-desk: the TypeScript project saved as front-desk\.zip · \d+ B\n$/);
    expect(readFileSync(join(root, "front-desk.zip")).equals(zip)).toBe(true);
  });

  it("--json answers the gateway's agent", async () => {
    answer("get", "/v1/studio/agents", { agents: [AN_AGENT] });
    expect(await runJson(["studio", "list"])).toEqual([AN_AGENT]);
  });
});
