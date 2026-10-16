/** A service's Context for a test: the fake gateway's URL and key, a project folder, and an IO that keeps what was said. */

import type { Env } from "../../src/api/client.js";
import { createContext, type Context } from "../../src/context.js";
import { CollectingIO } from "../../src/kit/io.js";
import { GATEWAY, KEY } from "./gateway.js";
import { folder, project } from "./project.js";

export interface TestContext {
  ctx: Context;
  io: CollectingIO;
}

export interface ContextOptions {
  /** The project's root; a project of one agent, `front-desk`, when left out. */
  cwd?: string;
  env?: Env;
  /** The key the environment holds; `null` for none. */
  key?: string | null;
  /** This machine's `~/.pinecall`; an empty folder of its own when left out. */
  home?: string;
}

/** A Context over the fake gateway, in the sandbox unless asked. */
export function testContext(options: ContextOptions = {}): TestContext {
  const io = new CollectingIO();
  const key = options.key === undefined ? KEY : options.key;
  const ctx = createContext({
    io,
    processEnv: { PINECALL_URL: GATEWAY, PINECALL_HOME: options.home ?? folder(), ...(key === null ? {} : { PINECALL_KEY: key }) },
    cwd: options.cwd ?? project(),
  });
  ctx.env = options.env ?? "sandbox";
  return { ctx, io };
}
