/** The CLI's own socket beside the agent's process: it takes no call, and answers the console's screens. */

import { createRequire } from "node:module";

import { aLostSocket, Pinecall } from "@pinecall/agents/client";

import type { Context } from "../context.js";
import { resendCallerNumber } from "../telephony/service.js";
import type { AgentHome } from "../project/layout.js";
import { devHandler, screensFor, type Screen } from "./handlers/index.js";
import type { Serving } from "./serving.js";

const { version } = createRequire(import.meta.url)("../../package.json") as { version: string };

/** How the companion names itself in the org's list of processes, apart from the agent's own. */
export const COMPANION_SDK = `pinecall-cli/${version}`;

/** The same companion beside an agent `pinecall mcp` holds in a thread. */
export const MCP_COMPANION_SDK = `pinecall-mcp/${version}`;

/** Whether an app of the org's list is a companion: it answers the console and takes no call, so nothing attaches to it. */
export function isCompanion(sdk: string | null): boolean {
  return sdk !== null && (sdk.startsWith("pinecall-cli/") || sdk.startsWith("pinecall-mcp/"));
}

/** The companion socket, and what closing it lets go. */
export interface Companion {
  pc: Pinecall;
  close(): Promise<void>;
}

/**
 * Hold every agent with `answersDev`: the console's verbs come here, the calls never do, and no
 * declaration is sent, so the agent's process's own stands. Connect it after the agents registered,
 * so there is a declaration to inherit.
 */
export function createCompanion(ctx: Context, homes: AgentHome[], serving: Serving, sdk: string = COMPANION_SDK): Companion {
  const gw = ctx.gateway();
  const pc = new Pinecall({ url: gw.url, apiKey: gw.key, env: gw.env, sdk });
  const screens: Screen[] = [];
  for (const home of homes) {
    const own = screensFor({ ctx, home, served: { slug: home.name, app: () => serving.app(home.name) } });
    screens.push(...own);
    pc.agent(home.name, { takesUnclaimed: false, answersDev: true }).onDev(devHandler(own));
  }
  // The agent's process says when the gateway is lost and back; here only an error of our own.
  pc.onErrors((failed) => {
    if (!aLostSocket(failed)) ctx.io.warn(failed.stack ?? failed.message);
  });
  // The gateway keeps a developer's phone only while a socket of their key is up: said on every connect.
  pc.onConnected(() => {
    if (gw.env !== "production") void resendCallerNumber(ctx).catch(() => undefined);
  });
  return {
    pc,
    async close(): Promise<void> {
      await Promise.allSettled(screens.map((screen) => screen.close?.()));
      pc.close();
    },
  };
}
