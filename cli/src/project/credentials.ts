/** Where the key and gateway URL come from: the environment, else the nearest `.env`, else the project's `pinecall.json` and this machine's sign-in. */

import { relative } from "node:path";

import { accountsGateway, createOrgKey, listOrgs } from "../api/accounts.js";
import type { Env } from "../api/client.js";
import { errorMessage } from "../errors.js";
import { nearestDotenv, readDotenv } from "../kit/dotenv.js";
import { findProjectConfig, PROJECT_FILE, type FoundConfig } from "./config.js";
import { keepOrgKey, keyIn, readSignIn, SESSION_FILE } from "./session.js";

/** Pinecall's cloud: the default gateway, serving both envs. */
export const CLOUD_URL = "https://cloud.pinecall.io";

/** Environment variables for the key and the gateway URL — a server's and CI's way in. */
export const KEY_VARIABLE = "PINECALL_KEY";
export const URL_VARIABLE = "PINECALL_URL";

/** The gateway a verb talks to, the key it sends, where the key came from, and the org it acts in. */
export interface Credentials {
  url: string;
  key: string | undefined;
  /** `the environment`, the `.env` path relative to the cwd, `your sign-in (…)`, or `nowhere`. */
  source: string;
  /** The org, when this machine's sign-in says it: the project's, or the sign-in's own. */
  org?: string;
  /** With no key: the sentence that says what to do. */
  missing?: string;
}

export const NO_KEY =
  "this machine is signed in nowhere: `pinecall login [url]` (a server keeps PINECALL_KEY in its secrets), or `pinecall-runtime setup` runs a runtime here that the CLI uses by itself";

/**
 * `PINECALL_KEY` and `PINECALL_URL` from the environment, else from the nearest `.env`; else the
 * project's `pinecall.json` names the gateway and the org, and the key is this machine's in that
 * org; outside a project, the sign-in at the gateway signed in to last, in its own org. Never
 * throws: what is wrong is said in `missing`. v1's `PINECALL_API_KEY` is never read.
 */
export function readCredentials(env: NodeJS.ProcessEnv, from: string, home: string): Credentials {
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
  let project: FoundConfig | undefined;
  try {
    project = findProjectConfig(from);
  } catch (failed) {
    return { url: CLOUD_URL, key: undefined, source: "nowhere", missing: errorMessage(failed) };
  }
  const session = `your sign-in (${home}/${SESSION_FILE})`;
  if (project !== undefined) {
    const { gateway, org } = project.config;
    const inOrg = keyIn(home, gateway, org);
    if (inOrg !== undefined) return { url: gateway, key: inOrg, source: session, org };
    const missing =
      readSignIn(home, gateway) === undefined
        ? `${relative(from, project.file) || PROJECT_FILE} runs this project at ${gateway}: sign in there, \`pinecall login ${gateway}\``
        : `this machine has no key in ${org} at ${gateway}: you are no member of it there, or the gateway refused one (\`pinecall login ${gateway}\` again)`;
    return { url: gateway, key: undefined, source: "nowhere", org, missing };
  }
  const signed = readSignIn(home);
  if (signed !== undefined) return { url: signed.url, key: signed.key, source: session, ...(signed.org === undefined ? {} : { org: signed.org }) };
  return { url: env[URL_VARIABLE] ?? CLOUD_URL, key: undefined, source: "nowhere", missing: NO_KEY };
}

/**
 * Before a verb runs: a project whose `pinecall.json` names an org this machine has no key in yet —
 * a project cloned onto it, an org switched in the file — gets one, minted from the sign-in at its
 * gateway and kept beside it. Asks the gateway only then; a failure is left for the verb to say.
 */
export async function prepareProjectKey(env: NodeJS.ProcessEnv, from: string, home: string): Promise<void> {
  if (readCredentials(env, from, home).key !== undefined) return;
  let project: FoundConfig | undefined;
  try {
    project = findProjectConfig(from);
  } catch {
    return;
  }
  if (project === undefined) return;
  const { gateway, org } = project.config;
  const signed = readSignIn(home, gateway);
  if (signed === undefined) return;
  try {
    const gw = accountsGateway(gateway, signed.key);
    const found = (await listOrgs(gw)).find((one) => one.member !== false && (one.slug === org || one.org === org));
    if (found === undefined) return;
    keepOrgKey(home, gateway, org, found.here ? signed.key : await createOrgKey(gw, found.org));
  } catch {
    return;
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

/** The sentence for a server token used against the other env. */
export function anotherEnvsToken(token: Env, url: string): string {
  const fix = token === "production" ? "run the verb with --prod" : "run the verb without --prod";
  return `this PINECALL_KEY is a ${token} server's token, made at ${url}: ${fix}`;
}
