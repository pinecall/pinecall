/** `pinecall mcp install` into a home of the test's own: written where each assistant reads it, replaced not merged, taken out, and no key anywhere. */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { inJson, inToml } from "../../../src/mcp/install/configs.js";
import { entryFor, hosts, PACKAGE } from "../../../src/mcp/install/hosts.js";
import { installEverywhere, listHosts } from "../../../src/mcp/install/installing.js";
import { folder } from "../../support/project.js";

const ENTRY = { command: "npx", args: ["-y", PACKAGE, "mcp"] };

describe("the config files", () => {
  it("JSON: the entry replaced under its key, the rest kept; null takes it out", () => {
    const written = inJson(JSON.stringify({ theme: "dark", mcpServers: { pinecall: { command: "old" }, other: { command: "x" } } }), "f.json", "mcpServers", ENTRY);
    expect(JSON.parse(written)).toEqual({ theme: "dark", mcpServers: { pinecall: ENTRY, other: { command: "x" } } });
    expect(JSON.parse(inJson(written, "f.json", "mcpServers", null)).mcpServers).toEqual({ other: { command: "x" } });
    expect(() => inJson("{not json", "f.json", "mcpServers", ENTRY)).toThrow("f.json is not valid JSON: fix it first");
  });

  it("TOML: one section replaced as text, comments kept", () => {
    const before = '# my codex\nmodel = "o5"\n\n[mcp_servers.pinecall]\ncommand = "old"\nargs = []\n\n[mcp_servers.other]\ncommand = "x"\n';
    const after = inToml(before, "mcp_servers", ENTRY);
    expect(after).toContain('# my codex\nmodel = "o5"');
    expect(after).toContain('[mcp_servers.pinecall]\ncommand = "npx"\nargs = ["-y", "pinecall@latest", "mcp"]\n');
    expect(after).toContain('[mcp_servers.other]\ncommand = "x"');
    expect(inToml("", "mcp_servers", ENTRY)).toBe('[mcp_servers.pinecall]\ncommand = "npx"\nargs = ["-y", "pinecall@latest", "mcp"]\n');
    expect(inToml(after, "mcp_servers", null)).not.toContain("pinecall");
  });
});

describe("every assistant", () => {
  it("installed ones get the entry, a backup beside the file first; absent ones are skipped", () => {
    const home = folder();
    mkdirSync(join(home, ".claude"));
    writeFileSync(join(home, ".claude.json"), JSON.stringify({ projects: {} }));
    mkdirSync(join(home, ".codex"));
    const done = installEverywhere(false, home);
    expect(done.filter((one) => one.did !== "not installed").map((one) => [one.host.name, one.did])).toEqual([["claude", "added"], ["codex", "added"]]);
    const claude = JSON.parse(readFileSync(join(home, ".claude.json"), "utf8")) as { projects: unknown; mcpServers: { pinecall: { args: string[] } } };
    expect(claude.projects).toEqual({});
    expect(claude.mcpServers.pinecall.args).toEqual(["-y", PACKAGE, "mcp"]);
    expect(existsSync(join(home, ".claude.json.bak"))).toBe(true);
    expect(readFileSync(join(home, ".claude.json"), "utf8") + readFileSync(join(home, ".codex/config.toml"), "utf8")).not.toMatch(/pc_(live|test)_|PINECALL_KEY/);
  });

  it("run again is a replace; --remove takes it out; --list says where each stands", () => {
    const home = folder();
    mkdirSync(join(home, ".cursor"));
    installEverywhere(false, home);
    expect(installEverywhere(false, home).find((one) => one.host.name === "cursor")?.did).toBe("replaced");
    expect(listHosts(home).find((one) => one.host.name === "cursor")?.state).toBe("registered");
    expect(installEverywhere(true, home).find((one) => one.host.name === "cursor")?.did).toBe("removed");
    expect(installEverywhere(true, home).find((one) => one.host.name === "cursor")?.did).toBe("not there");
  });

  it("a terminal assistant launches npx by name; the newest published CLI, never a project's pinned one", () => {
    const claude = hosts(folder()).find((one) => one.name === "claude")!;
    expect(entryFor(claude)).toEqual(ENTRY);
  });
});
