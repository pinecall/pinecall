/** Where a project's key and gateway URL come from: the environment, else the nearest `.env`, else the runtime on this machine. */

import { existsSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

import type { Env } from "../api/client.js";
import { nearestDotenv, readDotenv } from "../kit/dotenv.js";

/** Pinecall's cloud: the default gateway, serving both envs. */
export const CLOUD_URL = "https://cloud.pinecall.io";

/** Environment variables for the key and the gateway URL — the only two the CLI reads. */
export const KEY_VARIABLE = "PINECALL_KEY";
export const URL_VARIABLE = "PINECALL_URL";

/**
 * The file `pinecall-runtime setup` writes in the CLI's home when it runs a runtime on this
 * machine: that runtime's URL and a key of its org `default`, owner-only. Read last, so a project
 * with a key of its own (a Cloud project) never sees it.
 */
export const LOCAL_FILE = "local.json";

/** The project's gateway, its key if any, and where the key was read. */
export interface Credentials {
  url: string;
  key: string | undefined;
  /** `the environment`, `nowhere`, the `.env` path relative to the cwd, or `the local runtime (…)`. */
  source: string;
}

/** What `pinecall-runtime setup` wrote: where the runtime on this machine answers, and its key. */
export interface LocalRuntime {
  url: string;
  key: string;
}

/**
 * Read `PINECALL_KEY` and `PINECALL_URL` from the environment, else from the nearest `.env`, else
 * the runtime on this machine when `home` holds the file `setup` wrote. v1's `PINECALL_API_KEY`
 * is deliberately ignored: another CLI may export it for a different org.
 */
export function readCredentials(env: NodeJS.ProcessEnv, from: string, home?: string): Credentials {
  const exported = env[KEY_VARIABLE];
  if (exported !== undefined && exported !== "") {
    return { url: env[URL_VARIABLE] ?? CLOUD_URL, key: exported, source: "the environment" };
  }
  const file = nearestDotenv(from);
  const values = file === undefined ? {} : readDotenv(file);
  const key = values[KEY_VARIABLE];
  if (key !== undefined && key !== "") {
    return { url: env[URL_VARIABLE] ?? values[URL_VARIABLE] ?? CLOUD_URL, key, source: relative(from, file!) || file! };
  }
  const local = home === undefined ? undefined : readLocalRuntime(home);
  if (local !== undefined) return { url: local.url, key: local.key, source: `the local runtime (${join(home!, LOCAL_FILE)})` };
  return { url: env[URL_VARIABLE] ?? values[URL_VARIABLE] ?? CLOUD_URL, key: undefined, source: "nowhere" };
}

/** The runtime `pinecall-runtime setup` left in the CLI's home, when there is one. */
export function readLocalRuntime(home: string): LocalRuntime | undefined {
  const path = join(home, LOCAL_FILE);
  if (!existsSync(path)) return undefined;
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as Partial<LocalRuntime>;
    if (typeof parsed.url !== "string" || typeof parsed.key !== "string" || parsed.key === "") return undefined;
    return { url: parsed.url, key: parsed.key };
  } catch {
    return undefined;
  }
}

/**
 * The sandbox for a sandbox server's token (`pc_test_`); undefined for any other key. A person's
 * key is minted `pc_live_` too (it opens both envs), so only the sandbox's prefix says a server's
 * env before the request; the gateway refuses a production server's token asked for the sandbox.
 */
export function serverEnvOf(key: string): Env | undefined {
  return key.startsWith("pc_test_") ? "sandbox" : undefined;
}

export const NO_KEY =
  "no PINECALL_KEY here: `pinecall link` in the project's folder writes it to .env (a server keeps it in its secrets), or `pinecall-runtime setup` runs a runtime on this machine the CLI finds by itself";

/** The sentence for a server token used against the other env. */
export function anotherEnvsToken(token: Env, url: string): string {
  const fix = token === "production" ? "run the verb with --prod" : "run the verb without --prod";
  return `this PINECALL_KEY is a ${token} server's token, made at ${url}: ${fix}`;
}
