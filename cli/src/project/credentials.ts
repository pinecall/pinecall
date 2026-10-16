/** Where a project's key and gateway URL come from: the environment, else the nearest `.env`. */

import { relative } from "node:path";

import type { Env } from "../api/client.js";
import { nearestDotenv, readDotenv } from "../kit/dotenv.js";

/** Pinecall's cloud: the default gateway, serving both envs. */
export const CLOUD_URL = "https://cloud.pinecall.io";

/** Environment variables for the key and the gateway URL — the only two the CLI reads. */
export const KEY_VARIABLE = "PINECALL_KEY";
export const URL_VARIABLE = "PINECALL_URL";

/** The project's gateway, its key if any, and where the key was read. */
export interface Credentials {
  url: string;
  key: string | undefined;
  /** `the environment`, `nowhere`, or the `.env` path relative to the cwd. */
  source: string;
}

/**
 * Read `PINECALL_KEY` and `PINECALL_URL` from the environment, else from the nearest `.env`.
 * v1's `PINECALL_API_KEY` is deliberately ignored: another CLI may export it for a different org.
 */
export function readCredentials(env: NodeJS.ProcessEnv, from: string): Credentials {
  const exported = env[KEY_VARIABLE];
  if (exported !== undefined && exported !== "") {
    return { url: env[URL_VARIABLE] ?? CLOUD_URL, key: exported, source: "the environment" };
  }
  const file = nearestDotenv(from);
  if (file === undefined) return { url: env[URL_VARIABLE] ?? CLOUD_URL, key: undefined, source: "nowhere" };
  const values = readDotenv(file);
  const key = values[KEY_VARIABLE];
  return {
    url: env[URL_VARIABLE] ?? values[URL_VARIABLE] ?? CLOUD_URL,
    key: key === "" ? undefined : key,
    source: relative(from, file) || file,
  };
}

/**
 * The sandbox for a sandbox server's token (`pc_test_`); undefined for any other key. A person's
 * key is minted `pc_live_` too (it opens both envs), so only the sandbox's prefix says a server's
 * env before the request; the gateway refuses a production server's token asked for the sandbox.
 */
export function serverEnvOf(key: string): Env | undefined {
  return key.startsWith("pc_test_") ? "sandbox" : undefined;
}

export const NO_KEY = "no PINECALL_KEY here: `pinecall link` in the project's folder writes it to .env (a server keeps it in its secrets)";

/** The sentence for a server token used against the other env. */
export function anotherEnvsToken(token: Env, url: string): string {
  const fix = token === "production" ? "run the verb with --prod" : "run the verb without --prod";
  return `this PINECALL_KEY is a ${token} server's token, made at ${url}: ${fix}`;
}
