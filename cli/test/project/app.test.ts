// The project's voice app as `start` hands it on: asked of the project's own framework, never loaded here.

import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { servedApp } from "../../src/project/app.js";

/** A project with one agent, an `app.ts` at its root, and a framework whose serve entry does what `serve` says. */
function projectWhoseFramework(serve: string): { root: string; agents: string[] } {
  const root = mkdtempSync(join(tmpdir(), "served-app-"));
  const framework = join(root, "node_modules", "@pinecall", "agents");
  mkdirSync(framework, { recursive: true });
  writeFileSync(join(framework, "package.json"), JSON.stringify({ name: "@pinecall/agents", type: "module", exports: { "./serve": "./serve.mjs" } }));
  writeFileSync(join(framework, "serve.mjs"), serve);
  mkdirSync(join(root, "agents", "desk"), { recursive: true });
  writeFileSync(join(root, "agents", "desk", "agent.ts"), "");
  writeFileSync(join(root, "app.ts"), "");
  return { root, agents: [join(root, "agents", "desk", "agent.ts")] };
}

describe("the voice app start hands to the serve entry", () => {
  it("is the root's app file, when the project's framework describes it", async () => {
    const { root, agents } = projectWhoseFramework(`console.log(JSON.stringify({ name: "brightside", page: null }));`);
    expect(await servedApp(root, agents, process.env)).toBe(join(root, "app.ts"));
  });

  // A project on a framework from before voice apps, with an app.ts of its own (an Express server): the new
  // CLI passed `--app`, and its serve entry left with "Unknown option '--app'".
  it("is none for a framework that has no word for a voice app: the project is served as it was", async () => {
    const { root, agents } = projectWhoseFramework(`console.error("usage: serve start --file <agent.tsx> --slug <slug>"); process.exit(2);`);
    expect(await servedApp(root, agents, process.env)).toBeUndefined();
  });

  it("is refused in the framework's own sentence when the file is no voice app", async () => {
    const { root, agents } = projectWhoseFramework(`console.error("app.ts is read as the project's voice app, and its default export is none"); process.exit(2);`);
    await expect(servedApp(root, agents, process.env)).rejects.toThrow(/is read as the project's voice app/);
  });

  it("is none where the project has no app file", async () => {
    const root = mkdtempSync(join(tmpdir(), "served-app-"));
    expect(await servedApp(root, [join(root, "agents", "desk", "agent.ts")], process.env)).toBeUndefined();
  });
});
