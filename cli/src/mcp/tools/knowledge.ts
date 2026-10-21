/** The `docs`, `memory` and `remember` tools: the knowledge domain, over its service. */

import { z } from "zod";

import * as render from "../../knowledge/render.js";
import * as service from "../../knowledge/service/index.js";
import { tool, ToolRefused } from "../tool.js";
import { AGENT } from "./fields.js";

export const docs = tool({
  name: "docs",
  description: "The documents the agent searches: a folder pushed as a base, attached to the agent, held to its golden; the org's bases and who reads them.",
  schema: {
    action: z.enum(["push", "list", "eval", "attach", "detach", "attached"]).describe("push the agent's docs folder as a base; list the org's bases; eval scores the docs golden; attach a base to the agent; detach it; attached says which agents read which base"),
    agent: AGENT,
    base: z.string().optional().describe("the base's name; the agent's own when left out"),
    language: z.string().optional().describe("`push`: the language the files are written in (en, es, pt, fr, de, it, nl); counted from their words when left out"),
    k: z.number().int().min(1).max(50).optional().describe("`attach` and `eval`: how many chunks a turn reads"),
    mode: z.enum(["retrieved", "tool"]).optional().describe("`attach`: searched before every turn, or a tool the model calls"),
    min_score: z.number().min(0).max(1).optional().describe("`attach`: chunks under this share of the best one are dropped"),
    team: z.boolean().optional().describe("`attach` and `detach`: in the team's settings instead of your own"),
  },
  manual:
    "`docs push` sends the Markdown under `agents/<agent>/docs/` as a base (replacing it whole: push again after every edit); `attach` makes the agent search it before every turn; `eval` scores the questions in `agents/<agent>/test/goldens/docs.json` against it (recall@k, nDCG@10, by code). `list` and `attached` are the org's, and name no agent. Dropping a base is never a tool: `pinecall docs drop` in a terminal.",
  handler: async (args, ctx) => {
    if (args.action === "list") return await service.listBases(ctx);
    if (args.action === "attached") return { attached: render.attachments(await service.listAttached(ctx)) };
    if (args.action === "push") return (await service.pushDocs(ctx, { agent: args.agent, base: args.base, language: args.language }))[0];
    if (args.action === "eval") return (await service.evalDocs(ctx, { agent: args.agent, base: args.base, k: args.k }))[0];
    const base = args.base ?? ctx.agent(`docs ${args.action}`, { agent: args.agent }).name;
    if (args.action === "attach") {
      const done = await service.attachBase(ctx, service.AttachBaseInput.parse({ base, k: args.k, mode: args.mode, minScore: args.min_score, agent: args.agent, team: args.team === true }));
      return { ...done, said: render.attached(done) };
    }
    const done = await service.detachBase(ctx, service.DetachBaseInput.parse({ base, agent: args.agent, team: args.team === true }));
    return { ...done, said: render.detached(done) };
  },
});

export const memory = tool({
  name: "memory",
  description: "What the agent remembers about a caller, what it is told to keep and never keep, and the recall golden held against it.",
  schema: {
    action: z.enum(["show", "policy", "eval"]).describe("show what memory kept about `contact`; policy reads, or with remember/forget writes, what the agent keeps; eval scores the memory golden"),
    agent: AGENT,
    contact: z.string().optional().describe("`show`: the caller, by number or id"),
    remember: z.array(z.string()).optional().describe("`policy`: what is worth keeping about a caller, in your own words, one phrase each"),
    forget: z.array(z.string()).optional().describe("`policy`: what is never kept"),
    k: z.number().int().min(1).max(50).optional().describe("`eval`: how many facts a turn recalls"),
  },
  manual:
    "`memory policy` says what the agent keeps about a caller (`remember`) and never keeps (`forget`); with neither it reads them, and with no policy the agent remembers nothing. `show` reads what it kept about one caller, and names no agent; `eval` scores `agents/<agent>/test/goldens/memory.json`. Forgetting a caller is never a tool: `pinecall memory forget` in a terminal.",
  handler: async (args, ctx) => {
    if (args.action === "show") {
      if (args.contact === undefined) throw new ToolRefused("show takes the caller: a number or a contact id");
      return await service.showContact(ctx, args.contact);
    }
    if (args.action === "eval") return await service.evalMemory(ctx, { agent: args.agent, k: args.k });
    const { agent, answer } = await service.policy(ctx, service.PolicyInput.parse({ agent: args.agent, remember: args.remember, forget: args.forget, team: false }));
    const kept = service.cornerRead(answer)?.config.memory;
    return { agent, remember: kept?.remember ?? [], forget: kept?.forget ?? [] };
  },
});

export const remember = tool({
  name: "remember",
  description: "Hold memory's writing to its cases: each written call in agents/<agent>/test/memory/ run through one extraction, and what it kept checked by code.",
  schema: { agent: AGENT, grep: z.string().optional().describe("only cases whose name holds this") },
  manual:
    "`remember` runs the extraction cases under `agents/<agent>/test/memory/` — a written call and what memory must and must never keep from it — on the model and policy of the agent wherever it is held (the copy `start` holds when it holds it in the env asked), scored by code. Nothing is started.",
  handler: async (args, ctx) => await service.remember(ctx, service.RememberInput.parse({ agent: args.agent, grep: args.grep })),
});
