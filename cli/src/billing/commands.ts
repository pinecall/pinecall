/** `pinecall limits`: what the org may use in this env, what it used this month, and whose keys its calls run on. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import * as render from "./render.js";
import * as service from "./service.js";

const LIMITS = `
Every limit the deployment gave the org in this env — the sandbox's, or production's with
--prod — as what is used of it. A limit with no number is no limit; 0 is a limit that refuses
everything. Minutes, messages, LLM tokens, evals, simulations and the budget (dollars spent, both
envs together) are this month's and start again on the first (UTC); the rest are what the org holds
now: calls at once, agents, seats, bought numbers, hosted apps, memory facts and knowledge chunks.
A bought number counts; a number imported from the org's own carrier account never does.

The last line is whose keys a call runs on: the vendors the org brought keys for
(\`pinecall providers add\`), and the ones the runtime lends it. A vendor in neither refuses the
call before it starts — bring a key for it.

Examples
  $ pinecall limits
  sandbox
    minutes         12 of 30 · starts again 1 Nov
    evals           40 of 100 · starts again 1 Nov
    simulations     3, no limit
    bought numbers  0 of 0
    …
    keys            yours: anthropic · lent by the runtime: google, cartesia, deepgram
`;

export function register(program: Command, ctx: Context): void {
  program
    .command("limits")
    .description("what the org may use in this env, what it used this month, and whose keys its calls run on")
    .addHelpText("after", LIMITS)
    .action(async () => ctx.io.result(await service.getLimits(ctx), render.limits));
}
