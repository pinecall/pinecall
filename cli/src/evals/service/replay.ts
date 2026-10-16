/** Ring 3: one finished call rebuilt from its log and answered by the runtime's code checks; nothing re-run, no model asked. */

import * as api from "../../api/evals.js";
import type { Context } from "../../context.js";
import { readJsonFile } from "../../kit/json-file.js";

export type { Replayed, ReplayPolicy, Verdict } from "../../api/evals.js";

/** The code checks over one call, with the words banned and the latency budgets of the policy file, if any. */
export async function replayCall(ctx: Context, call: string, policy: api.ReplayPolicy = {}): Promise<api.Replayed> {
  return api.replayCall(ctx.gateway(), call, policy);
}

/** A policy file: `{"banned": […], "budget": {…}}`; read before any request, so a bad path fails as a usage error. */
export function readPolicy(file: string | undefined): api.ReplayPolicy {
  return file === undefined ? {} : readJsonFile<api.ReplayPolicy>("--policy", file);
}
