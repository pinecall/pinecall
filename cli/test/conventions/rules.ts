/** The twelve rules of CONTRIBUTING.md, each a function over the source tree that answers the lines that break it. */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "../../src");

/** The domains, bottom up: a domain imports one below it, never one above. */
export const DOMAINS = ["billing", "accounts", "providers", "agents", "knowledge", "telephony", "judging", "calls", "evals", "hosting", "studio", "alerts", "scaffold", "dev", "mcp"] as const;

/** The folders that are not domains, and what each may be imported by anyone. */
const FOUNDATIONS = new Set(["api", "kit", "project"]);
const ROOT_FILES = new Set(["main.ts", "program.ts", "context.ts", "errors.ts", "version.ts"]);

/** What a domain folder holds: these three, as a module or a folder of modules. */
const A_DOMAINS_FILES = new Set(["commands", "service", "render"]);
/** The engines hold modules of their own. */
const ENGINES = new Set(["dev", "mcp"]);

/** Other programs: a child spawned to play audio, and the code a worker thread runs. */
const OTHER_PROGRAMS = new Set(["kit/ear.ts", "mcp/agent-host/thread.ts"]);

const MOST_LINES = 400;
const MOST_LINES_AT_THE_TOP = 150;

/** Words the vocabulary bans as names of ours; a wire field read off a shape (`answer.world`) is the wire's. */
export const BANNED = ["door", "theDoor", "Door", "Door_", "world", "knocked", "asked", "Refused", "Refusal", "CannotRun", "keyFrom", "Numbering", "Turning", "Wording"] as const;

/** One source file: its path under src/, its text, its lines. */
export interface Source {
  path: string;
  text: string;
  lines: string[];
}

/** Every .ts under src/, sorted. */
export function sources(root: string = SRC): Source[] {
  const found: string[] = [];
  const walk = (folder: string): void => {
    for (const name of readdirSync(folder).sort()) {
      const path = join(folder, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (name.endsWith(".ts")) found.push(path);
    }
  };
  walk(root);
  return found.map((path) => {
    const text = readFileSync(path, "utf8");
    return { path: relative(root, path), text, lines: text.split("\n") };
  });
}

/** The relative imports of a file that exist at runtime (`import type` is erased), each resolved to a path under src/. */
export function importsOf(source: Source): string[] {
  const found: string[] = [];
  const text = source.text.replace(/import\s+type\s+[^;]+;/g, "");
  for (const match of text.matchAll(/from\s+"(\.[^"]+)"|import\s*\(\s*"(\.[^"]+)"\s*\)/g)) {
    const said = match[1] ?? match[2]!;
    found.push(relative(SRC, resolve(SRC, dirname(source.path), said)).replace(/\.js$/, ".ts"));
  }
  return found;
}

/** The domain a path belongs to, or undefined for the foundations and the root. */
export function domainOf(path: string): (typeof DOMAINS)[number] | undefined {
  const top = path.split("/")[0]!;
  return (DOMAINS as readonly string[]).includes(top) ? (top as (typeof DOMAINS)[number]) : undefined;
}

/** The file's kind within its domain: commands, service, render, or the engine's own module. */
function kindOf(path: string): string {
  const parts = path.split("/");
  return parts[1]?.replace(/\.ts$/, "") ?? "";
}

/** Rule 1 — canon: a domain folder holds commands, service and render, each a module or a folder of them. */
export function canon(all: Source[]): string[] {
  return all
    .filter((one) => domainOf(one.path) !== undefined && !ENGINES.has(domainOf(one.path)!))
    .filter((one) => !A_DOMAINS_FILES.has(kindOf(one.path)) && one.path.split("/")[1] !== "help.ts")
    .map((one) => `${one.path}: a domain holds commands, service and render only`);
}

/** Rule 2 — layers: commands and tools never import api/; a service never imports commands, render or mcp; api/ stands on kit and errors; no domain imports one above it. */
export function layers(all: Source[]): string[] {
  const broken: string[] = [];
  const rank = new Map<string, number>(DOMAINS.map((name, at) => [name, at]));
  for (const one of all) {
    const from = domainOf(one.path);
    const kind = kindOf(one.path);
    for (const target of importsOf(one)) {
      const top = target.split("/")[0]!;
      const to = domainOf(target);
      if ((kind === "commands" || one.path.startsWith("mcp/tools/")) && top === "api") broken.push(`${one.path} imports ${target}: a command or a tool asks the service, never the gateway`);
      if (kind === "service" && to === from && ["commands", "render"].includes(kindOf(target))) broken.push(`${one.path} imports ${target}: a service never imports its command or its render`);
      if (kind === "service" && to === "mcp" && from !== "mcp") broken.push(`${one.path} imports ${target}: a service never imports the MCP`);
      if (top === "api" && !["api", "kit"].includes(target.split("/")[0]!) && !["errors.ts"].includes(target)) broken.push(`${one.path} imports ${target}: api/ stands on kit, errors and the SDK alone`);
      if (from !== undefined && to !== undefined && to !== from) {
        if (rank.get(to)! > rank.get(from)!) broken.push(`${one.path} imports ${target}: ${to} is above ${from}`);
        if (!ENGINES.has(from) && !["service", "render"].includes(kindOf(target))) broken.push(`${one.path} imports ${target}: another domain's service or render, never its commands`);
      }
      if (ROOT_FILES.has(one.path) && to !== undefined && one.path !== "program.ts") broken.push(`${one.path} imports ${target}: the root stands below every domain`);
    }
  }
  return [...broken, ...cycles(all)];
}

/** No cycles among modules. */
export function cycles(all: Source[]): string[] {
  const edges = new Map(all.map((one) => [one.path, importsOf(one).filter((target) => !target.endsWith(".d.ts"))]));
  const state = new Map<string, "visiting" | "done">();
  const found: string[] = [];
  const visit = (path: string, trail: string[]): void => {
    const seen = state.get(path);
    if (seen === "done") return;
    if (seen === "visiting") {
      const loop = trail.slice(trail.indexOf(path));
      // Type-only imports are erased and cannot cycle at runtime; a cycle of them is still a smell, reported once.
      found.push(`cycle: ${[...loop, path].join(" → ")}`);
      return;
    }
    state.set(path, "visiting");
    for (const next of edges.get(path) ?? []) if (edges.has(next)) visit(next, [...trail, path]);
    state.set(path, "done");
  };
  for (const path of edges.keys()) visit(path, []);
  return found;
}

/** Rule 3 — the gateway at home: `fetch(` and `/v1/` only in api/. */
export function gatewayAtHome(all: Source[]): string[] {
  return all
    .filter((one) => !one.path.startsWith("api/"))
    .flatMap((one) => lines(one, /\bfetch\(|["`]\/v1\//).map((at) => `${one.path}:${at}: fetch and /v1/ live in api/`));
}

/** Rule 4 — output at home: the process's streams only in kit/io.ts; `process.exit` nowhere; a service never prints. */
export function outputAtHome(all: Source[]): string[] {
  const broken: string[] = [];
  for (const one of all) {
    if (OTHER_PROGRAMS.has(one.path)) continue;
    if (one.path !== "kit/io.ts") broken.push(...lines(one, /process\.(stdout|stderr)\b|\bconsole\.(log|error|warn|info|debug|table)\(/).map((at) => `${one.path}:${at}: output goes through kit/io`));
    broken.push(...lines(one, /process\.exit\(/).map((at) => `${one.path}:${at}: main.ts returns the code; nothing exits`));
    if (kindOf(one.path) === "service") broken.push(...lines(one, /\.io\.(result|print)\(/).map((at) => `${one.path}:${at}: a service returns data; the command renders it`));
  }
  return broken;
}

/** Rule 9 — size: a module is at most 400 lines; main.ts and program.ts at most 150. */
export function size(all: Source[]): string[] {
  return all
    .filter((one) => one.lines.length - 1 > (["main.ts", "program.ts"].includes(one.path) ? MOST_LINES_AT_THE_TOP : MOST_LINES))
    .map((one) => `${one.path}: ${one.lines.length - 1} lines`);
}

/** Rule 10 — never the framework: client and wire only; no serve entry imported; nothing listens on a port. */
export function neverTheFramework(all: Source[]): string[] {
  return all.flatMap((one) => [
    ...lines(one, /from "@pinecall\/agents"|from "@pinecall\/agents\/serve/).map((at) => `${one.path}:${at}: the CLI imports @pinecall/agents/client and /wire alone`),
    ...lines(one, /\.listen\(/).map((at) => `${one.path}:${at}: nothing listens on a port`),
  ]);
}

/** Rule 12 — every file opens with one line saying what it is. */
export function docstrings(all: Source[]): string[] {
  return all
    .filter((one) => {
      const first = one.lines[0]?.startsWith("#!") ? one.lines[1] : one.lines[0];
      return first === undefined || !/^\/\*\* .+ \*\/$/.test(first);
    })
    .map((one) => `${one.path}: the first line is one /** sentence */`);
}

/** Rule 8 — boring names: a banned word is never declared as a name of ours (a parameter or a wire field may carry it). */
export function vocabulary(all: Source[]): string[] {
  const declared = new RegExp(`\\b(?:const|let|var|function|class|interface|type|enum)\\s+(?:${BANNED.join("|")})\\b`);
  return all.flatMap((one) => lines(one, declared).map((at) => `${one.path}:${at}: a banned word is a name here`));
}

/** Rule 11, the half the tree can check — tests mirror src/: every test file names a source file or a convention. */
export function mirrors(tests: Source[], all: Source[]): string[] {
  const known = new Set(all.map((one) => one.path));
  return tests
    .filter((one) => !one.path.startsWith("conventions/") && !one.path.startsWith("support/") && !one.path.startsWith("mcp/pages"))
    .filter((one) => !known.has(one.path.replace(/\.test\.ts$/, ".ts")) && !known.has(one.path.replace(/\.test\.ts$/, "/index.ts")))
    .map((one) => `test/${one.path}: no src/${one.path.replace(/\.test\.ts$/, ".ts")} to mirror`);
}

/** Every rule at once, for a script or a test. */
export function everyRule(all: Source[] = sources()): Record<string, string[]> {
  return {
    canon: canon(all),
    layers: layers(all),
    gatewayAtHome: gatewayAtHome(all),
    outputAtHome: outputAtHome(all),
    size: size(all),
    neverTheFramework: neverTheFramework(all),
    docstrings: docstrings(all),
    vocabulary: vocabulary(all),
  };
}

// The 1-based lines of a file that match, comments and strings included: a rule reads the text as a reviewer would.
function lines(source: Source, pattern: RegExp): number[] {
  return source.lines.flatMap((line, at) => (pattern.test(line) && !line.trimStart().startsWith("//") && !line.trimStart().startsWith("*") ? [at + 1] : []));
}
