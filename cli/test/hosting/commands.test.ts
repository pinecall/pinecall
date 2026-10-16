/** `pinecall deploy` as typed: up by default, followed until live or not, the apps and releases as lines, logs fresh or stale. */

import { describe, expect, it } from "vitest";

import { answer, stream } from "../support/gateway.js";
import { project } from "../support/project.js";
import { run } from "../support/run.js";

const SERVED = { "package.json": JSON.stringify({ dependencies: { "@pinecall/agents": "^0.10.1" } }) };
const A_RELEASE = { name: "clinica", release: 4, sha256: "9f86d081884c7d659a2feaa0c55ad015", bytes: 20_480, author: "ana@clinica.test", note: "fix the greeting", created_at: 1_792_150_000 };
const AN_APP = { name: "clinica", release: 4, live_release: 3, failed_why: null, stopped: false, created_by: "ana@clinica.test", created_at: 1_792_000_000 };

describe("pinecall deploy", () => {
  it("alone uploads this folder and follows the release until it is live", async () => {
    answer("post", "/v1/hosted/:name/releases", A_RELEASE);
    stream("/v1/events");
    answer("get", "/v1/hosted", { apps: [{ ...AN_APP, live_release: 4 }] });
    const ran = await run(["deploy", "--name", "clinica"], { cwd: project(["front-desk"], SERVED) });
    expect(ran.code).toBe(0);
    expect(ran.out).toBe("clinica: release 4 sent · 20 KB · 9f86d081884c\n");
    expect(ran.err).toContain("clinica: release 4 is live");
  });

  it("exits 1 when the release failed, and says what serves", async () => {
    answer("post", "/v1/hosted/:name/releases", A_RELEASE);
    stream("/v1/events");
    answer("get", "/v1/hosted", { apps: [{ ...AN_APP, failed_why: "npm ci exited 1" }] });
    const ran = await run(["deploy", "--name", "clinica"], { cwd: project(["front-desk"], SERVED) });
    expect(ran.code).toBe(1);
    expect(ran.err).toContain("release 4 failed — release 3 keeps serving");
  });

  it("--no-follow uploads and returns", async () => {
    const sent = answer("post", "/v1/hosted/:name/releases", A_RELEASE);
    const ran = await run(["deploy", "up", "--name", "clinica", "--note", "fix the greeting", "--no-follow"], { cwd: project(["front-desk"], SERVED) });
    expect(ran.code).toBe(0);
    expect(sent[0]!.query).toEqual({ note: "fix the greeting" });
  });

  it("refuses a project that does not depend on the framework, before anything is sent", async () => {
    const ran = await run(["deploy", "--name", "clinica"]);
    expect(ran.code).toBe(2);
    expect(ran.err).toContain("npm i @pinecall/agents");
  });

  it("list says what serves and why the newest failed", async () => {
    answer("get", "/v1/hosted", { apps: [{ ...AN_APP, failed_why: "npm ci exited 1\nmore" }, { ...AN_APP, name: "sales", release: null, live_release: null }] });
    const ran = await run(["deploy", "list"]);
    expect(ran.out).toBe("clinica  live: release 3 · release 4 failed: npm ci exited 1\nsales    no release yet\n");
  });

  it("releases prints one line each, newest first, the note last", async () => {
    answer("get", "/v1/hosted/:name/releases", { releases: [A_RELEASE] });
    const ran = await run(["deploy", "releases", "--name", "clinica"]);
    expect(ran.out).toMatch(/^ {3}4 {2}\d{4}-\d{2}-\d{2} \d{2}:\d{2} {5}20 KB {2}ana@clinica\.test {2}fix the greeting\n$/);
  });

  it("rollback refuses a release that is no number", async () => {
    expect((await run(["deploy", "rollback", "latest", "--name", "clinica"])).code).toBe(2);
  });

  it("logs prints the fresh lines", async () => {
    answer("get", "/v1/hosted/:name/releases", { releases: [] });
    stream("/v1/hosted/:name/logs", [{ name: "clinica", host: "runner-1", lines: "registered front-desk\n", at: Date.now() / 1000 + 60 }]);
    const ran = await run(["deploy", "logs", "--name", "clinica"]);
    expect(ran.code).toBe(0);
    expect(ran.out).toBe("registered front-desk\n");
  });

  it("stop, start and rm say what each did", async () => {
    answer("post", "/v1/hosted/:name/stop");
    answer("post", "/v1/hosted/:name/start");
    const removed = answer("delete", "/v1/hosted/:name");
    expect((await run(["deploy", "stop", "--name", "clinica"])).out).toContain("clinica: stopped");
    expect((await run(["deploy", "start", "--name", "clinica"])).out).toContain("clinica: started");
    expect((await run(["deploy", "rm", "--name", "clinica"])).out).toContain("no longer hosted, its token revoked");
    expect(removed[0]!.path).toBe("/v1/hosted/clinica");
  });
});
