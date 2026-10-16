/** Hosting against the gateway: a release refused before it is sent, uploaded as a tarball, followed on the feed; the logs read. */

import { describe, expect, it } from "vitest";

import { UsageError } from "../../src/errors.js";
import * as service from "../../src/hosting/service.js";
import { answer, stream } from "../support/gateway.js";
import { testContext } from "../support/context.js";
import { project, write } from "../support/project.js";

const SERVED = JSON.stringify({ name: "clinica", dependencies: { "@pinecall/agents": "^0.10.1" } });
const A_RELEASE = { name: "clinica", release: 4, sha256: "9f86d081884c7d659a2feaa0c55ad015", bytes: 20_480, author: "ana@clinica.test", note: "", created_at: 1_792_150_000 };
const AN_APP = { name: "clinica", release: 4, live_release: 3, failed_why: null, stopped: false, created_by: "ana@clinica.test", created_at: 1_792_000_000 };

describe("the app's name", () => {
  it("is the one given, else the folder's, and must be a slug", () => {
    const { ctx } = testContext();
    expect(service.appName(ctx, "support")).toBe("support");
    expect(() => service.appName(ctx, "Support Desk")).toThrow(UsageError);
  });
});

describe("a release", () => {
  it("is refused when the project does not depend on the framework", async () => {
    const { ctx } = testContext({ cwd: project(["front-desk"], { "package.json": JSON.stringify({ dependencies: {} }) }) });
    await expect(service.uploadRelease(ctx, "clinica", "")).rejects.toThrow(service.NOT_SERVABLE(["@pinecall/agents"]));
  });

  it("is refused for an agent in another language: Pinecall hosts TypeScript", async () => {
    const root = project([], { "package.json": SERVED });
    write(root, "agents/sales/agent.rb", "class Sales < Pinecall::Agent; end\n");
    const { ctx } = testContext({ cwd: root });
    await expect(service.uploadRelease(ctx, "clinica", "")).rejects.toThrow(/Pinecall hosts TypeScript projects/);
  });

  it("is uploaded as a gzipped tarball, its note in the query, cut to a line", async () => {
    const sent = answer("post", "/v1/hosted/:name/releases", A_RELEASE);
    const { ctx } = testContext({ cwd: project(["front-desk"], { "package.json": SERVED, ".env": "PINECALL_KEY=never-sent" }) });
    expect(await service.uploadRelease(ctx, "clinica", "x".repeat(300))).toEqual({ name: "clinica", release: 4, bytes: 20_480, sha256: A_RELEASE.sha256 });
    expect(sent[0]!.type).toBe("application/gzip");
    expect(sent[0]!.query["note"]).toHaveLength(200);
    expect(sent[0]!.body).toBeDefined();
  });

  it("rolls back to a release by its number, which must be one", async () => {
    const sent = answer("post", "/v1/hosted/:name/rollback", { ...A_RELEASE, release: 5 });
    const { ctx } = testContext();
    await expect(service.rollbackRelease(ctx, "clinica", 0)).rejects.toBeInstanceOf(UsageError);
    expect((await service.rollbackRelease(ctx, "clinica", 3)).release).toBe(5);
    expect(sent[0]!.body).toEqual({ release: 3 });
  });
});

describe("where a release stands", () => {
  it("is live, replaced, failed, or still on its way", () => {
    expect(service.standingOf({ ...AN_APP, live_release: 4 }, 4)).toEqual({ live: true, line: "clinica: release 4 is live" });
    expect(service.standingOf({ ...AN_APP, release: 5 }, 4)?.line).toBe("release 4 was replaced by release 5 before it went live");
    expect(service.standingOf({ ...AN_APP, failed_why: "npm ci exited 1" }, 4)).toEqual({ live: false, line: "clinica: release 4 failed — release 3 keeps serving\nnpm ci exited 1" });
    expect(service.standingOf(AN_APP, 4)).toBeUndefined();
  });

  it("is read when the feed opens, and the follow ends once it is settled", async () => {
    const feed = stream("/v1/events");
    answer("get", "/v1/hosted", { apps: [{ ...AN_APP, live_release: 4 }] });
    const { ctx } = testContext();
    expect(await service.followRelease(ctx, "clinica", 4, 5_000)).toEqual({ live: true, line: "clinica: release 4 is live" });
    expect(feed[0]!.query).toEqual({ types: "release.changed" });
  });

  it("is null when the time is up first", async () => {
    stream("/v1/events");
    answer("get", "/v1/hosted", { apps: [AN_APP] });
    const { ctx } = testContext();
    expect(await service.followRelease(ctx, "clinica", 4, 100)).toBeNull();
  });
});

describe("the logs", () => {
  it("are the first read sent after the ask", async () => {
    stream("/v1/hosted/:name/logs", [{ name: "clinica", host: "runner-1", lines: "registered front-desk\nlistening\n", at: Date.now() / 1000 + 60 }]);
    const { ctx } = testContext();
    expect(await service.readLogs(ctx, "clinica", 5_000)).toEqual({ name: "clinica", lines: "registered front-desk\nlistening\n", staleBy: null, none: false });
  });

  it("are said stale when only an older read came within the wait", async () => {
    stream("/v1/hosted/:name/logs", [{ name: "clinica", host: "runner-1", lines: "old\n", at: Date.now() / 1000 - 30 }]);
    const { ctx } = testContext();
    const found = await service.readLogs(ctx, "clinica", 100);
    expect(found.lines).toBe("old\n");
    expect(found.staleBy).toBeGreaterThanOrEqual(30);
  });

  it("are none when the runner never sent any", async () => {
    stream("/v1/hosted/:name/logs", [{ name: "clinica", host: null, lines: "", at: null }]);
    const { ctx } = testContext();
    expect((await service.readLogs(ctx, "clinica", 100)).none).toBe(true);
  });

  it("a follow prints only the lines after the part two reads share", () => {
    expect(service.newLines("a\nb\nc\n", "b\nc\nd\ne\n")).toEqual(["d", "e"]);
    expect(service.newLines("a\n", "x\ny\n")).toEqual(["x", "y"]);
    expect(service.newLines("a\nb\n", "a\nb\n")).toEqual([]);
  });
});
