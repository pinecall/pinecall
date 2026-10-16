/** The `providers` tool: the providers domain, over its service. */

import * as service from "../../providers/service.js";
import { tool } from "../tool.js";

export const providers = tool({
  name: "providers",
  description: "The vendors an agent may run on: what each does, whether it is ready, and whose key it would run on. Never a key.",
  schema: {},
  manual:
    "`providers` lists every speech, model and voice vendor this gateway can run, what each does, and whose key a call would use. Bringing a key of your own is never a tool: the person types `pinecall providers add <vendor>` in a terminal, or uses the console.",
  handler: async (_args, ctx) => await service.listProviders(ctx),
});
