/** The console's addresses: the sandbox's under `/sandbox`, production's at the root, signed in with a one-use code. */

import type { Env } from "../api/client.js";
import { GatewayError, errorMessage } from "../errors.js";

// A 404 on the login-code endpoint means the gateway predates this CLI.
const NO_SUCH_ENDPOINT = 404;
const OLDER_GATEWAY = "this gateway has no login-code endpoint, so it is older than this CLI. Restart it: it serves the console too, and that will be stale as well.";

// What a person does first with an agent they just started: talk to it, in the console's chat.
export const TALK = "playground";

// One gateway serves both consoles: production's at `/`, the sandbox's under `/sandbox`.
function consoleRoot(url: string, env: Env): string {
  const gateway = url.replace(/\/$/, "");
  return env === "production" ? gateway : `${gateway}/sandbox`;
}

/**
 * Console URL carrying a one-use login code (valid five minutes), so the browser gets its own key
 * and this process's key never appears in a URL.
 */
export function consoleUrl(url: string, env: Env, slug: string | undefined, code: string, screen = ""): string {
  const at = slug === undefined ? "/" : `/a/${encodeURIComponent(slug)}${screen === "" ? "" : `/${screen}`}`;
  return `${consoleRoot(url, env)}${at}?login=${encodeURIComponent(code)}`;
}

/** The console's own address for an agent, with no code: what a page asks a person to sign in to. */
export function consoleAddress(url: string, env: Env, slug: string, screen = ""): string {
  return `${consoleRoot(url, env)}/a/${encodeURIComponent(slug)}${screen === "" ? "" : `/${screen}`}`;
}

/** Why no console URL could be made, in the gateway's words. */
export function whyNoConsole(failed: unknown): string {
  if (failed instanceof GatewayError) return failed.status === NO_SUCH_ENDPOINT ? OLDER_GATEWAY : failed.message;
  return errorMessage(failed);
}
