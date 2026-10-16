/** The assistants `pinecall mcp install` writes into: where each keeps its MCP servers, in which format, under which key. */

import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, dirname, join } from "node:path";

export const SERVER = "pinecall";

/** The package an assistant launches: always the newest published one. */
export const PACKAGE = "pinecall@latest";

/** One assistant's config file. */
export interface Host {
  name: string;
  label: string;
  /** The config file, absolute. */
  file: string;
  format: "json" | "toml";
  /** The table of MCP servers in that file. */
  key: string;
  /** What proves the assistant is installed even before it ever wrote its config. */
  sign: string;
  /** A desktop app is launched without the shell's PATH: it is given npx by its full path, and node's folder on its PATH. */
  desktop?: true;
}

/** The command an assistant launches: the published CLI, as the server. */
export interface Entry {
  command: string;
  args: string[];
  /** A desktop app's only: the PATH npx and the CLI need to find this machine's node. Never a key. */
  env?: { PATH: string };
}

// Claude Desktop keeps its config where each system keeps an app's.
function desktopFolder(home: string, env: NodeJS.ProcessEnv): string {
  if (process.platform === "darwin") return join(home, "Library", "Application Support", "Claude");
  if (process.platform === "win32") return join(env["APPDATA"] ?? join(home, "AppData", "Roaming"), "Claude");
  return join(home, ".config", "Claude");
}

/** Every assistant this machine might have. */
export function hosts(home: string = homedir(), env: NodeJS.ProcessEnv = process.env): Host[] {
  const at = (path: string): string => join(home, path);
  const desktop = desktopFolder(home, env);
  return [
    { name: "claude", label: "Claude Code", file: at(".claude.json"), format: "json", key: "mcpServers", sign: at(".claude") },
    { name: "claude-desktop", label: "Claude Desktop", file: join(desktop, "claude_desktop_config.json"), format: "json", key: "mcpServers", sign: desktop, desktop: true },
    { name: "codex", label: "Codex", file: at(".codex/config.toml"), format: "toml", key: "mcp_servers", sign: at(".codex") },
    { name: "cursor", label: "Cursor", file: at(".cursor/mcp.json"), format: "json", key: "mcpServers", sign: at(".cursor") },
    { name: "windsurf", label: "Windsurf", file: at(".codeium/windsurf/mcp_config.json"), format: "json", key: "mcpServers", sign: at(".codeium/windsurf") },
    { name: "antigravity", label: "Antigravity", file: at(".gemini/antigravity/mcp_config.json"), format: "json", key: "mcpServers", sign: at(".gemini/antigravity") },
    // The settings file, not `.gemini`: Antigravity nests under that folder too.
    { name: "gemini", label: "Gemini CLI", file: at(".gemini/settings.json"), format: "json", key: "mcpServers", sign: at(".gemini/settings.json") },
  ];
}

/** Whether the assistant is on this machine. */
export function installed(host: Host): boolean {
  return existsSync(host.sign) || existsSync(host.file);
}

/**
 * What the assistant launches: the newest published CLI, by name. Not the bare name — inside a project
 * that pins an older `pinecall`, npx would run that one, which has no `mcp`, and the assistant
 * would only see the connection close. No key is ever written here: the server reads the project's.
 */
export function entryFor(host: Host): Entry {
  const args = ["-y", PACKAGE, "mcp"];
  const nodes = dirname(process.execPath);
  const beside = join(nodes, process.platform === "win32" ? "npx.cmd" : "npx");
  if (host.desktop !== true || !existsSync(beside)) return { command: "npx", args };
  // npx and the CLI both start with `#!/usr/bin/env node`: node has to be on the PATH they are given.
  return { command: beside, args, env: { PATH: [nodes, "/usr/local/bin", "/usr/bin", "/bin"].join(delimiter) } };
}
