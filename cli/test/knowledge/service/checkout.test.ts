/** The folder as a checkout of the base: each file of the base written or left alone, the folder's own kept and named, one file taken out of the base. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { GatewayError } from "../../../src/errors.js";
import * as service from "../../../src/knowledge/service/checkout.js";
import { answer, refuse } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { folder, project } from "../../support/project.js";

const ROW = { chars: 7, chunks: 1, pushed_at: 1_792_150_000 };
const LISTED = { base: "front-desk", kept: true, files: [{ path: "hours.md", ...ROW }, { path: "policies/insurance.md", ...ROW }] };
const TEXTS: Record<string, string> = { "hours.md": "# Hours\n9 to 5", "policies/insurance.md": "# Insurance" };

// The gateway's file endpoint, answering each path's text; a path keeps its slashes, so msw's `*` takes it.
function filesAnswered(): ReturnType<typeof answer> {
  return answer("get", "/v1/knowledge/:base/files/*", ({ path }) => {
    const file = decodeURIComponent(path.replace(/^\/v1\/knowledge\/[^/]+\/files\//, ""));
    return { path: file, text: TEXTS[file], chunks: 1, pushed_at: 1_792_150_000 };
  });
}

describe("pull", () => {
  it("writes each file of the base where its path says, leaves one whose text is the same, and keeps the folder's own", async () => {
    const root = project(["front-desk"], { "agents/front-desk/docs/hours.md": "# Hours\n9 to 5", "agents/front-desk/docs/old.md": "# Old", "agents/front-desk/docs/README.md": "# What goes here" });
    answer("get", "/v1/knowledge/:base", LISTED);
    const read = filesAnswered();
    const { ctx } = testContext({ cwd: root });
    const dir = join(root, "agents/front-desk/docs");
    const done = await service.pullDocs(ctx, {});
    expect(done).toEqual({
      base: "front-desk",
      dir,
      kept: true,
      files: [
        { path: "hours.md", file: join(dir, "hours.md"), status: "unchanged" },
        { path: "policies/insurance.md", file: join(dir, "policies/insurance.md"), status: "written" },
        { path: "old.md", file: join(dir, "old.md"), status: "kept" },
      ],
    });
    expect(readFileSync(join(dir, "policies/insurance.md"), "utf8")).toBe("# Insurance");
    expect(readFileSync(join(dir, "old.md"), "utf8")).toBe("# Old");
    expect(read.map((one) => one.path)).toEqual(["/v1/knowledge/front-desk/files/hours.md", "/v1/knowledge/front-desk/files/policies/insurance.md"]);
  });

  it("a folder and a base both named need no project, and the folder is made when it is not there", async () => {
    answer("get", "/v1/knowledge/:base", { ...LISTED, base: "faq", files: [LISTED.files[0]] });
    filesAnswered();
    const dir = join(folder(), "docs");
    const { ctx } = testContext({ cwd: folder() });
    const done = await service.pullDocs(ctx, { dir, base: "faq" });
    expect(done.files).toEqual([{ path: "hours.md", file: join(dir, "hours.md"), status: "written" }]);
  });

  it("writes nothing outside the folder, whatever path the gateway sends", async () => {
    answer("get", "/v1/knowledge/:base", { ...LISTED, files: [{ path: "../agent.ts", ...ROW }] });
    const { ctx } = testContext();
    await expect(service.pullDocs(ctx, {})).rejects.toThrow(/outside .*agents\/front-desk\/docs: not written/);
  });

  it("a base the gateway keeps no files of answers none, and says so", async () => {
    answer("get", "/v1/knowledge/:base", { base: "front-desk", kept: false, files: [] });
    const { ctx } = testContext();
    expect(await service.pullDocs(ctx, {})).toMatchObject({ kept: false, files: [] });
  });

  it("a base the env has not is the gateway's 404, said as it is", async () => {
    refuse("get", "/v1/knowledge/:base", 404, "no base front-desk in sandbox");
    const { ctx } = testContext();
    await expect(service.pullDocs(ctx, {})).rejects.toThrow(GatewayError);
    await expect(service.pullDocs(ctx, {})).rejects.toThrow("no base front-desk in sandbox");
  });
});

describe("rm", () => {
  it("takes one file out of the agent's base, its path's segments escaped one by one", async () => {
    const sent = answer("delete", "/v1/knowledge/:base/files/*");
    const { ctx } = testContext();
    expect(await service.removeDoc(ctx, service.RemoveDocInput.parse({ path: "policies/insurance plan.md" }))).toEqual({ base: "front-desk", path: "policies/insurance plan.md" });
    expect(sent[0]!.path).toBe("/v1/knowledge/front-desk/files/policies/insurance%20plan.md");
  });

  it("--base names another base, from any folder", async () => {
    const sent = answer("delete", "/v1/knowledge/:base/files/*");
    const { ctx } = testContext({ cwd: folder() });
    await service.removeDoc(ctx, service.RemoveDocInput.parse({ path: "hours.md", base: "faq" }));
    expect(sent[0]!.path).toBe("/v1/knowledge/faq/files/hours.md");
  });

  it("a file the base has not is the gateway's 404, said as it is", async () => {
    refuse("delete", "/v1/knowledge/:base/files/*", 404, "no file prices.md in the base front-desk");
    const { ctx } = testContext();
    await expect(service.removeDoc(ctx, service.RemoveDocInput.parse({ path: "prices.md" }))).rejects.toThrow("no file prices.md in the base front-desk");
  });
});
