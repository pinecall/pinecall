/** The entry: the server built from its environment, listening until it is told to stop. */

import { createServer } from "node:http";

import { HOSTED_STAGES, version, whoHolds } from "pinecall/hosted";

import { Keys } from "./keys.js";
import { listener } from "./server.js";
import { IDLE_MS, Sessions } from "./sessions.js";
import { readSettings } from "./settings.js";

// An image is checked by this before it is pushed: everything imports, and the tools are there.
const CHECK = "--check";
// Longer than a tool waits (50 s) and than the load balancer keeps a quiet connection.
const KEEP_ALIVE_MS = 620_000;
const DRAIN_MS = 55_000;

/** Run the server; resolves with the process's exit code once it stopped. */
export async function main(argv: readonly string[], env: NodeJS.ProcessEnv): Promise<number> {
  const say = (line: string): void => void process.stderr.write(`${line}\n`);
  const tools = HOSTED_STAGES.flatMap((stage) => stage.tools).length;
  if (argv.includes(CHECK)) {
    say(`pinecall-mcp ${version()} · ${tools} tools`);
    return tools > 0 ? 0 : 1;
  }
  let settings;
  try {
    settings = readSettings(env);
  } catch (failed) {
    say(`pinecall-mcp: ${failed instanceof Error ? failed.message : String(failed)}`);
    return 2;
  }
  const keys = new Keys((key) => whoHolds(settings.gateway, key));
  const sessions = new Sessions(settings.gateway);
  const server = createServer(listener({ settings, keys, sessions, log: say }));
  server.keepAliveTimeout = KEEP_ALIVE_MS;
  server.headersTimeout = KEEP_ALIVE_MS + 1000;
  const sweeping = setInterval(() => void sessions.sweep(), IDLE_MS / 6);
  await new Promise<void>((listening) => server.listen(settings.port, "0.0.0.0", listening));
  say(`pinecall-mcp ${version()} · ${tools} tools · ${settings.address}/mcp on :${settings.port} · gateway ${settings.gateway}`);

  // Told to stop: no new connection is taken, the requests in flight end, and every call is hung up.
  await new Promise<void>((told) => {
    process.once("SIGTERM", told);
    process.once("SIGINT", told);
  });
  clearInterval(sweeping);
  const drained = new Promise<void>((closed) => server.close(() => closed()));
  server.closeIdleConnections();
  await Promise.race([drained, new Promise((late) => setTimeout(late, DRAIN_MS).unref())]);
  await sessions.close();
  return 0;
}
