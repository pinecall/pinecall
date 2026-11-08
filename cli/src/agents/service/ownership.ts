/** Who sets an agent: a Studio agent is set here, an app written as code by its code and nothing else. */

import * as agents from "../../api/agents.js";
import { GatewayClient } from "../../api/client.js";
import * as hosting from "../../api/hosting.js";
import type { Context } from "../../context.js";
import { GatewayError, UsageError } from "../../errors.js";

type Kind = "code" | "studio";

/** What an agent no list names counts as: a class that is not connected now is the common case, and its code is what sets it. */
const NAMED_BY_NO_LIST: Kind = "code";

export const SET_IN_ITS_CODE = (agent: string): string => `${agent} is set in its code: change it there and deploy`;

/** Every write of one agent's settings, lexicon, melody, bases or memory rules passes here first. */
export async function mustNotBeCode(ctx: Context, agent: string): Promise<void> {
  const kind = (await kindOf(ctx.gateway(), agent)) ?? NAMED_BY_NO_LIST;
  if (kind === "code") throw new UsageError(SET_IN_ITS_CODE(agent));
}

// The box's row first: it outlives a process, and a Studio agent has one from the moment it is made.
// A row of the held list counts next, for a key that may not read the box's (a supervisor's); a slug
// can be held twice, per scope, and a Studio agent is never also a class in one env.
async function kindOf(gw: GatewayClient, agent: string): Promise<Kind | undefined> {
  const [hosted, held] = await Promise.all([readable(hosting.listApps(gw)), readable(agents.listHeld(gw))]);
  const app = hosted.find((one) => one.name === agent);
  if (app !== undefined) return app.kind === "studio" ? "studio" : "code";
  const holds = held.filter((one) => one.slug === agent);
  if (holds.length > 0) return holds.some((one) => one.kind === "studio") ? "studio" : "code";
  // A Studio agent reaches production on its first deploy: until then its row is the sandbox's alone.
  if (gw.env !== "production") return undefined;
  const sandbox = await readable(hosting.listApps(new GatewayClient(gw.url, gw.key, "sandbox")));
  return sandbox.some((one) => one.name === agent && one.kind === "studio") ? "studio" : undefined;
}

// A list this key may not open says nothing about the agent; any other failure is the gateway's to say.
async function readable<Row>(list: Promise<Row[]>): Promise<Row[]> {
  try {
    return await list;
  } catch (failed) {
    if (failed instanceof GatewayError && (failed.status === 403 || failed.status === 404)) return [];
    throw failed;
  }
}
