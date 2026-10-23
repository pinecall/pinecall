/** The `line`, `numbers`, `carriers` and `callbacks` tools: the telephony domain, over its service. */

import { z } from "zod";

import * as service from "../../telephony/service.js";
import { tool, ToolRefused } from "../tool.js";
import { AGENT } from "./fields.js";

export const line = tool({
  name: "line",
  description: "Who answers the agent's number right now and who could take it; which phone is the person's own, so their calls reach their copy.",
  schema: {
    action: z.enum(["show", "from", "forget", "claim", "release"]).describe("show whose process a ring lands in; from says which phone is the person's own; forget drops it; claim takes the line for this copy; release gives it back"),
    agent: AGENT,
    number: z.string().optional().describe("`from`: the person's own phone, in +E.164"),
  },
  manual:
    "`line show` says whose process a ring at the agent's number lands in. `from <number>` says which phone is the person's own, once: their calls reach the copy they hold (the one `start` holds) while everybody else reaches production. `claim` takes the line for this copy, `release` gives it back, `forget` drops the phone.",
  handler: async (args, ctx) => {
    if (args.action === "from") {
      if (args.number === undefined) throw new ToolRefused("from takes the person's own phone, in +E.164");
      return await service.setCallerNumber(ctx, args.number);
    }
    if (args.action === "forget") return await service.forgetCallerNumber(ctx);
    const choice = { agent: args.agent };
    if (args.action === "claim") return await service.claimLine(ctx, choice);
    if (args.action === "release") return await service.releaseLine(ctx, choice);
    return await service.showLine(ctx, choice);
  },
});

export const numbers = tool({
  name: "numbers",
  description: "The org's numbers and the agent each reaches; the numbers its carrier accounts own; importing one, or buying one on the deployment's account, shown as steps before anything is written.",
  schema: {
    action: z.enum(["list", "available", "import", "buy"]).describe("list the org's numbers; available is what its carrier accounts own; import points one of them at an agent; buy gets a new one on the deployment's account — import and buy are a dry run unless dry_run is false"),
    number: z.string().optional().describe("`import`: the number, in +E.164"),
    agent: z.string().optional().describe("`import`, `buy`: the agent that answers it"),
    channel: z.enum(["phone", "whatsapp"]).optional().describe("`import`, `buy`: phone unless it is a WhatsApp number"),
    account: z.string().optional().describe("`available`, `import`: the carrier account the number lives in, when the org has several (`carriers list` names them)"),
    move: z.boolean().optional().describe("`import`: take the number off the trunk it is on now (another environment's, or another agent's), as a 409 naming that trunk asks"),
    country: z.string().optional().describe("`buy`: the country, two letters (ES, US)"),
    area_code: z.string().optional().describe("`buy`: an area code, digits only"),
    dry_run: z.boolean().optional().describe("`import`, `buy`: true (the default) answers the steps and writes nothing; false does them"),
  },
  manual:
    "`numbers list` shows which number reaches which agent in the sandbox; `available` what the org's carrier accounts own. `import` points a number an account owns at an agent; when the org has several accounts, name the one that owns it in `account`, or ask the person which. `buy` gets a new number in `country` (and `area_code`) on the deployment's own account and points it at the agent; a bought number counts against the org's `numbers` limit (`usage` shows it), an imported one never does. Both first answer the steps they would take and write nothing; call again with `dry_run: false` to do them, after the person agreed. Letting a number go is never a tool: `pinecall numbers drop` in a terminal.",
  handler: async (args, ctx) => {
    if (args.action === "available") return await service.listAvailableNumbers(ctx, args.account);
    if (args.action === "list") return { numbers: await service.listNumbers(ctx) };
    const dryRun = args.dry_run !== false;
    if (args.action === "buy") {
      if (args.country === undefined || args.agent === undefined) throw new ToolRefused("buy takes a country, two letters, and the agent that answers the number");
      return await service.buyNumber(ctx, service.BuyNumberInput.parse({ country: args.country, agent: args.agent, areaCode: args.area_code, channel: args.channel, dryRun }));
    }
    if (args.number === undefined || args.agent === undefined) throw new ToolRefused("import takes the number and the agent that answers it");
    return await service.importNumber(ctx, service.ImportNumberInput.parse({ number: args.number, agent: args.agent, account: args.account, channel: args.channel, move: args.move === true, dryRun }));
  },
});

export const carriers = tool({
  name: "carriers",
  description: "The org's carrier accounts — Twilio, a SIP peer, WhatsApp — and one account's networks and how outbound calls leave. Never a secret.",
  schema: { action: z.enum(["list", "show"]).describe("list the org's carrier accounts, or show one"), account: z.string().optional().describe("`show`: the account's id") },
  manual: "`carriers` lists the org's carrier accounts and shows one. Adding one takes its secrets, so it is never a tool: the person types `pinecall carriers add` in a terminal, or uses the console's Numbers screen.",
  handler: async (args, ctx) => {
    if (args.action === "show") return await service.showCarrier(ctx, args.account);
    return { carriers: await service.listCarriers(ctx) };
  },
});

export const callbacks = tool({
  name: "callbacks",
  description: "The callers waiting to be called back, oldest first: who, on which channel, through what (the overflow, the agent's own tool, the widget).",
  schema: { agent: z.string().optional().describe("only this agent's"), after: z.number().int().min(0).optional().describe("where the page before ended") },
  manual: "`callbacks` lists the people waiting for a call back, each with the call it came from.",
  handler: async (args, ctx) => await service.listCallbacks(ctx, service.ListCallbacksInput.parse(args)),
});
