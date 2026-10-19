/** The `studio` tool: the studio domain, over its service. */

import { z } from "zod";

import * as service from "../../studio/service.js";
import { tool, ToolRefused } from "../tool.js";
import { needed } from "./fields.js";

export const studio = tool({
  name: "studio",
  description: "Build an agent with no code, as the console's Studio does: made, its definition saved as releases, each tool's request tried, deployed to production.",
  schema: {
    action: z.enum(["list", "show", "new", "save", "try", "deploy"]).describe("list the org's Studio agents; show one's newest release and definition; new makes one; save keeps a whole definition as the next release; try sends one tool's request once; deploy puts the sandbox's release in production"),
    name: z.string().optional().describe("the agent's name: lower-case letters and digits joined by dashes; every action but list takes it"),
    definition: service.DefinitionInput.optional().describe("`save`: the whole definition, every part of it, as `show` answers it — what is left out is gone; `new`: what it starts as, the gateway's template when left out; `try`: a definition not saved yet, to try its tool before saving"),
    based_on: z.number().int().min(1).optional().describe("`save`: the release the definition was read at, from `show` or the last `save`; refused when someone saved meanwhile"),
    tool: z.string().optional().describe("`try`: the tool's name"),
    arguments: z.record(z.string(), z.unknown()).optional().describe("`try`: the tool's arguments, as the model would fill its params"),
    release: z.number().int().min(1).optional().describe("`deploy`: the sandbox's release to deploy; its newest when left out"),
    note: z.string().optional().describe("`new`, `save` and `deploy`: a note kept with the release"),
  },
  manual:
    "`studio` builds an agent with no class and no project: a definition the gateway holds and answers calls from. `new` makes it in the sandbox from a template; `show` answers its `release` and `definition`. `save` keeps a whole `definition` as the next release, `based_on` the release you read — refused when someone saved meanwhile: `show` again and save over that. A definition is the agent's `instructions`; its `greeting` (`say` the words, or `reply` for an opening of the model's own); its `tools`, each an HTTP request (`method`, `url`, `headers`, `params` the model fills: a path's `{name}`, else a GET's query or the JSON body) whose answer the model reads; and `collect`, the `fields` it gathers from the caller, the call ended once the required ones are in and the fields posted to `send_to`. `try` sends one tool's request once with `arguments` and answers its status, body and time: try every tool before a person calls. Then `chat` with `agent` set to its name talks to it, as to any sandbox agent, with nothing started. `deploy` is asked without `prod`: the sandbox's release lands in production, on a person's key that may act there. A secret is never written into a definition: a header names it as `{{secrets.NAME}}`, and the person sets it with `pinecall secrets set` or in the console. The `deploy` tool's `list` shows it beside the org's hosted apps; removing one is `pinecall deploy rm` in a terminal.",
  handler: async (args, ctx) => {
    if (args.action === "list") return { agents: await service.listAgents(ctx) };
    const name = needed(args.name, "name");
    switch (args.action) {
      case "new":
        return await service.createAgent(ctx, name, args.note ?? "", args.definition);
      case "save": {
        if (args.definition === undefined) throw new ToolRefused("save takes the whole `definition`: `show` answers the one standing");
        if (args.based_on === undefined) throw new ToolRefused("save takes `based_on`, the release the definition was read at: `show` answers it");
        return await service.saveAgent(ctx, name, args.definition, args.based_on, args.note ?? "");
      }
      case "try":
        return await service.tryTool(ctx, name, needed(args.tool, "tool"), args.arguments ?? {}, args.definition);
      case "deploy":
        return await service.deployAgent(ctx, name, args.release, args.note ?? "");
      default:
        return await service.getAgent(ctx, name);
    }
  },
});
