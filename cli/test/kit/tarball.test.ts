/** A project as a release: its files but its secrets and dependencies, one gzipped ustar archive. */

import { symlinkSync } from "node:fs";
import { join } from "node:path";
import { gunzipSync } from "node:zlib";

import { describe, expect, it } from "vitest";

import { folderFiles, isLeftOut, projectFiles, tarball } from "../../src/kit/tarball.js";
import { folder, write } from "../support/project.js";

describe("a release", () => {
  it("leaves out dependencies, builds, git and every .env, and what a .gitignore names where it sits", () => {
    const root = folder();
    for (const path of ["package.json", "agents/front-desk/agent.ts", ".env", ".env.production", "node_modules/x/index.js", ".venv/bin/python", "agents/front-desk/__pycache__/agenda.pyc", "dist/main.js", "agents/front-desk/scratch.log", "agents/.gitignore"]) write(root, path, path === "agents/.gitignore" ? "*.log\n" : "x");
    expect(projectFiles(root)).toEqual(["agents/.gitignore", "agents/front-desk/agent.ts", "package.json"]);
    expect([isLeftOut(".env.local"), isLeftOut("src/.envoy.ts")]).toEqual([true, false]);
  });

  it("carries a page's built folder whole, though a release leaves builds out, and never an .env in it", () => {
    const root = folder();
    for (const path of ["package.json", ".gitignore", "ui/dist/index.html", "ui/dist/assets/app.js", "ui/dist/.env", "ui/src/main.tsx"]) write(root, path, path === ".gitignore" ? "dist\n" : "x");
    expect(projectFiles(root)).toEqual([".gitignore", "package.json", "ui/src/main.tsx"]);
    expect(folderFiles(root, "ui/dist")).toEqual(["ui/dist/assets/app.js", "ui/dist/index.html"]);
    expect(folderFiles(root, "ui/build")).toEqual([]);
  });

  it("a link in the folder is refused with the gateway's sentence, not skipped", () => {
    const root = folder();
    write(root, "package.json", "{}");
    symlinkSync("/etc/hosts", join(root, "link"));
    expect(() => projectFiles(root)).toThrow("link is a link or a device: a release holds files and folders only");
  });

  it("is one gzipped ustar archive, the files' paths and contents in it", () => {
    const root = folder();
    write(root, "package.json", '{"name":"clinica"}');
    const archive = gunzipSync(tarball(root, ["package.json"]));
    expect(archive.length % 512).toBe(0);
    expect(archive.subarray(0, 12).toString()).toBe("package.json");
    expect(archive.subarray(257, 262).toString()).toBe("ustar");
    expect(archive.subarray(512, 530).toString()).toBe('{"name":"clinica"}');
  });
});
