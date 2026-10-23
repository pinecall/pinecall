/** A project as a release: its files, never its secrets or its dependencies, as a gzipped tarball. */

import { existsSync, lstatSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { gzipSync } from "node:zlib";

import ignore, { type Ignore } from "ignore";

import { PinecallError, UsageError } from "../errors.js";

// The gateway's own sentence: a release holds files and folders, and a link is refused before it is sent.
export const NOT_A_FILE = (path: string): string => `${path} is a link or a device: a release holds files and folders only`;

// The box installs the dependencies itself; .env holds the keys, which travel as secrets instead.
const NEVER = new Set(["node_modules", ".venv", "__pycache__", ".git", "dist", ".pinecall", ".DS_Store"]);

const A_DOTENV = /^\.env(\..*)?$/;

const BLOCK = 512;

/** Whether a path of the project stays out of every release. */
export function isLeftOut(path: string): boolean {
  return path.split(/[\\/]/).some((part) => NEVER.has(part) || A_DOTENV.test(part));
}

/**
 * The project's files, relative and sorted: every file but what a `.gitignore` of the project names
 * (each read where it sits, as git reads it) and what `isLeftOut` names. No git is asked: a folder
 * that is no checkout, or a front that starts no process, packs the same release.
 */
export function projectFiles(root: string): string[] {
  return walked(root, root, []).filter((path) => !isLeftOut(path)).sort();
}

/** The files as one gzipped ustar archive: plain files, their paths and modes as the project has them. */
export function tarball(root: string, files: readonly string[]): Buffer {
  const blocks: Buffer[] = [];
  for (const path of files) {
    const content = readFileSync(join(root, path));
    const executable = (lstatSync(join(root, path)).mode & 0o111) !== 0;
    blocks.push(header(path, content.length, executable), content, Buffer.alloc((BLOCK - (content.length % BLOCK)) % BLOCK));
  }
  blocks.push(Buffer.alloc(BLOCK * 2));
  return gzipSync(Buffer.concat(blocks));
}

/** One `.gitignore` and the folder its patterns are read from. */
interface Ignored {
  from: string;
  rules: Ignore;
}

function walked(root: string, folder: string, ignoring: readonly Ignored[]): string[] {
  const here = join(folder, ".gitignore");
  const rules = existsSync(here) ? [...ignoring, { from: folder, rules: ignore().add(readFileSync(here, "utf8")) }] : ignoring;
  const found: string[] = [];
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name);
    if (NEVER.has(entry.name) || ignored(rules, path, entry.isDirectory())) continue;
    if (entry.isDirectory()) found.push(...walked(root, path, rules));
    else if (entry.isFile()) found.push(relative(root, path).split(sep).join("/"));
    else throw new UsageError(NOT_A_FILE(relative(root, path).split(sep).join("/")));
  }
  return found;
}

// A folder is matched with a trailing slash, so `build/` names it and not a file called build.
function ignored(rules: readonly Ignored[], path: string, folder: boolean): boolean {
  return rules.some(({ from, rules: one }) => one.ignores(`${relative(from, path).split(sep).join("/")}${folder ? "/" : ""}`));
}

// ustar: a name over 100 bytes is split at a slash into prefix (155) and name (100).
function header(path: string, size: number, executable: boolean): Buffer {
  const block = Buffer.alloc(BLOCK);
  const [prefix, name] = splitName(path);
  block.write(name, 0, 100, "utf8");
  block.write(executable ? "0000755\0" : "0000644\0", 100, 8, "ascii");
  block.write("0000000\0", 108, 8, "ascii");
  block.write("0000000\0", 116, 8, "ascii");
  block.write(`${size.toString(8).padStart(11, "0")}\0`, 124, 12, "ascii");
  block.write("00000000000\0", 136, 12, "ascii");
  block.write("        ", 148, 8, "ascii");
  block.write("0", 156, 1, "ascii");
  block.write("ustar\0", 257, 6, "ascii");
  block.write("00", 263, 2, "ascii");
  block.write(prefix, 345, 155, "utf8");
  const sum = block.reduce((total, byte) => total + byte, 0);
  block.write(`${sum.toString(8).padStart(6, "0")}\0 `, 148, 8, "ascii");
  return block;
}

function splitName(path: string): [string, string] {
  if (Buffer.byteLength(path) <= 100) return ["", path];
  const cut = path.lastIndexOf("/", 155);
  if (cut <= 0 || Buffer.byteLength(path.slice(cut + 1)) > 100) throw new PinecallError(`${path}: too long a path for a release`);
  return [path.slice(0, cut), path.slice(cut + 1)];
}
