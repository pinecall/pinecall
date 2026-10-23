/** A save reloads the agent: which files are saves, one reload per burst, the next copy answering before the one before drains, a broken save left unloaded. */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { isASave, onSaves, Releases, type Reloaded } from "../../src/dev/reload.js";

const tick = (): Promise<void> => new Promise((settled) => setImmediate(settled));

interface Copy {
  name: string;
  stopped: boolean;
  stop(): Promise<void>;
}

const copy = (name: string): Copy => ({
  name,
  stopped: false,
  async stop() {
    this.stopped = true;
  },
});

describe("what a save is", () => {
  it("the agent's own files are, and what its tools and package managers write is not", () => {
    for (const file of ["agent.tsx", "views/desk.tsx", "agent.rb", "agent.py", "prompts/greeting.md", "data/slots.json"]) expect(isASave(file), file).toBe(true);
    for (const file of ["node_modules/x/index.js", "dist/agent.js", ".pinecall/state.json", "test/goldens/a.json", "start.log", ".venv/lib/x.py", "__pycache__/a.pyc", ".env"]) expect(isASave(file), file).toBe(false);
  });
});

describe("the releases", () => {
  it("the next copy answers before the one before drains, and the version goes up", async () => {
    const told: Reloaded[] = [];
    const first = copy("v1");
    const releases = new Releases(first, async () => copy("v2"), (reloaded) => told.push(reloaded));
    await releases.reload();
    expect(releases.current.name).toBe("v2");
    expect(releases.version).toBe(2);
    expect(first.stopped).toBe(true);
    expect(told).toEqual([{ version: 2 }]);
  });

  it("a save that does not load keeps the copy before answering and says why, and the next save tries again", async () => {
    const told: Reloaded[] = [];
    const first = copy("v1");
    let loads = false;
    const releases = new Releases(
      first,
      async () => {
        if (!loads) throw new Error("agent.tsx(3,1): a type is missing");
        return copy("v2");
      },
      (reloaded) => told.push(reloaded),
    );
    await releases.reload();
    expect(releases.current).toBe(first);
    expect(first.stopped).toBe(false);
    expect(releases.broken).toBe("agent.tsx(3,1): a type is missing");
    expect(told).toEqual([{ version: 1, broken: "agent.tsx(3,1): a type is missing" }]);
    loads = true;
    await releases.reload();
    expect(releases.current.name).toBe("v2");
    expect(releases.broken).toBeUndefined();
  });

  it("reloads run one after another, each followed, and a closed one lets a copy that was starting go", async () => {
    let made = 0;
    let release: ((made: Copy) => void) | undefined;
    const followed: string[] = [];
    const releases = new Releases(copy("v1"), () => new Promise<Copy>((done) => ((release = done), (made += 1))));
    releases.onReplaced((current) => followed.push(current.name));
    const one = releases.reload();
    const two = releases.reload();
    await tick();
    expect(made).toBe(1);
    release!(copy("v2"));
    await one;
    await tick();
    expect(made).toBe(2);
    const closing = releases.close();
    const late = copy("v3");
    release!(late);
    await Promise.all([two, closing]);
    expect(releases.current.name).toBe("v2");
    expect(late.stopped).toBe(true);
    expect(followed).toEqual(["v2"]);
  });
});

describe("the watch", () => {
  it("a burst of saves is one reload, a log written beside the agent is none", async () => {
    const root = mkdtempSync(join(tmpdir(), "pinecall-reload-"));
    let saved = 0;
    const stop = onSaves([root], () => (saved += 1), 50);
    writeFileSync(join(root, "agent.tsx"), "export default class {}");
    writeFileSync(join(root, "agent.tsx"), "export default class A {}");
    writeFileSync(join(root, "start.log"), "a line\n");
    await new Promise((settled) => setTimeout(settled, 250));
    stop();
    expect(saved).toBe(1);
    writeFileSync(join(root, "agent.tsx"), "export default class B {}");
    await new Promise((settled) => setTimeout(settled, 150));
    expect(saved).toBe(1);
  });
});
