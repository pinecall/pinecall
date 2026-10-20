/** The `judges`, `judging` and `usage` tools: the judging domain, and the bill it makes, over the services. */

import { z } from "zod";

import * as billing from "../../billing/service.js";
import * as billingRender from "../../billing/render.js";
import * as render from "../../judging/render.js";
import * as service from "../../judging/service.js";
import { tool, ToolRefused } from "../tool.js";
import { AGENT } from "./fields.js";

export const judges = tool({
  name: "judges",
  description: "Every judge the agent's calls meet: Pinecall's, switched on or off; the org's own and the agent's own, written or dropped; one tried on finished calls; and how often each agreed with the labels people gave.",
  schema: {
    action: z.enum(["list", "add", "on", "off", "rm", "try", "agreement"]).describe("list every judge; add one of your own (the same name again replaces it); on/off one of Pinecall's; rm one of your own; try one on finished calls, writing nothing; agreement: how often each judge agreed with the labels people gave, and whether it is trusted"),
    agent: AGENT,
    org: z.boolean().optional().describe("the org's list: Pinecall's switched for every agent, and the org's own"),
    name: z.string().optional().describe("the judge's name: lowercase letters, digits and dashes"),
    asks: z.string().optional().describe("`add`, or `try` of one not yet saved: the question asked of the whole call"),
    answer: z.string().optional().describe("`verdict` (held or broken, the default), `score` (1 to 5), or `choice:a,b,c`"),
    when: z.string().optional().describe("`always` (the default), `simulations`, or `trigger:…` (a yes-or-no asked first; a no is N/A)"),
    reads: z.array(z.enum(service.READS)).optional().describe("what the judge reads beside the call"),
    last: z.number().int().min(1).max(50).optional().describe("`try`: the agent's newest finished calls"),
    calls: z.array(z.string()).optional().describe("`try`: the calls, by id, instead of `last`"),
  },
  manual:
    "`judges` is every question a model answers of the agent's finished calls, citing the turns. Pinecall's library (consent, grounded, promises, disclosed, identified, honoured-stop, ended-well, expected-outcome, relevance, repetition, sentiment; every one off until switched on) is switched with `on`/`off`, for the org (`org`) or one agent, and never dropped. Your own are written whole with `add`: a verdict, a score or a choice, on every call, simulations only or a trigger, reading the prompt, the evidence or the facts on request. Any judge may answer N/A, never billed; each that answers is one eval, not billed when the judge model is on the org's own key. `try` asks one judge — written, Pinecall's, or one only in this call's fields — of the agent's last calls and writes nothing. `agreement` is each judge against the labels people gave (`cases` with `judge_was_wrong`, or the console's Cases): labelled, compared, agreed, the rate, and `trusted` — null under `labels_to_judge` compared labels, then whether the rate reaches `agrees_at_least`.",
  handler: async (args, ctx) => {
    if (args.org === true && args.action === "try") throw new ToolRefused("try asks one agent's calls: name the agent, not the org");
    const owner = service.ownerOf(ctx, { org: args.org === true, agent: args.agent });
    if (args.action === "list") return await service.listJudges(ctx, owner);
    if (args.action === "agreement") return await service.agreement(ctx, owner);
    if (args.name === undefined) throw new ToolRefused("the judge's name is needed");
    const flags = { asks: args.asks, answer: args.answer, when: args.when, reads: args.reads?.join(",") };
    if (args.action === "rm") return await service.removeJudge(ctx, owner, args.name);
    if (args.action === "on" || args.action === "off") return await service.switchJudge(ctx, owner, args.name, args.action === "on");
    if (args.action === "add") return await service.addJudge(ctx, owner, args.name, flags);
    if ((args.last === undefined) === (args.calls === undefined)) throw new ToolRefused("try takes `last` or `calls`, one of them");
    return await service.tryJudge(ctx, { ...flags, name: args.name, agent: args.agent, last: args.last, calls: args.calls });
  },
});

export const judging = tool({
  name: "judging",
  description: "Whether the org's calls are judged at hang-up, and the model they are judged on: Pinecall's, or one of the org's own — on its own key, a local model among them, evals are never billed.",
  schema: {
    action: z.enum(["show", "set"]).describe("show how the org's calls are judged; set changes it"),
    on: z.boolean().optional().describe("`set`: judge the org's calls at hang-up, or not"),
    model: z.string().optional().describe("`set`: the judge model, vendor/model (`openai/gpt-5.4-mini`), or `platform` for Pinecall's"),
    options: z.record(z.string(), z.unknown()).optional().describe("`set`: the plugin's keyword arguments, `{\"base_url\": \"http://gpu:8000/v1\"}` for a model on the org's own server"),
  },
  manual:
    "`judging` is the org's: whether every call is judged at hang-up, and on which model. Pinecall's judge model is billed per eval (one judge that answered one call); a model the org names runs on its own key for that vendor — a local model's server through `options.base_url` among them — and then its evals are never billed. An agent's own `judge` setting (the `agent` tool) wins over this one. The model is tried on the org's keys in both envs when it is set, so a model nobody can key is refused here.",
  handler: async (args, ctx) => {
    if (args.action === "show") {
      const standing = await service.getJudging(ctx);
      return { ...standing, says: render.judging(standing) };
    }
    const platform = args.model === "platform";
    const input = service.SetJudgingInput.parse({ on: args.on, model: platform ? undefined : args.model, options: args.options, platform });
    const now = await service.setJudging(ctx, input);
    return { ...now, says: render.judging(now) };
  },
});

export const usage = tool({
  name: "usage",
  description: "What the org has used of its limits this month in the environment — minutes, messages, evals, simulations, bought numbers — whose keys its calls run on, and whether its judges cost it evals.",
  schema: {},
  manual:
    "`usage` answers “what does this cost?”: each quota as `{limit, used}` (a null limit is no limit; minutes, messages, evals and simulations start again on the first of the month, UTC), `keys` — the vendors the org brought keys for and the ones the runtime lends it; a vendor in neither refuses the call — and `evals_billed` — false when the org's judges run on its own key, where evals are never billed. Past `evals` a call's judges left are skipped; past `simulations` a simulation is refused. `billing_url` is where the org buys more, when the deployment sells plans.",
  handler: async (_args, ctx) => {
    const report = await billing.getLimits(ctx);
    const judgingNow = await service.getJudging(ctx);
    const model = judgingNow.model ?? null;
    const { limits } = report;
    return {
      environment: limits.world,
      minutes: limits.minutes,
      messages: limits.messages,
      evals: limits.evals,
      simulations: limits.simulations,
      concurrent_calls: limits.concurrent_calls,
      agents: limits.agents,
      seats: limits.seats,
      numbers: limits.numbers,
      keys: billingRender.keysLine(report.brought, limits.lends),
      evals_billed: judgingNow.on && !judgingNow.own_key,
      judge_model: model === null ? "Pinecall's" : `${model.provider}, on ${judgingNow.own_key ? "your own key" : "a key Pinecall lends"}`,
      billing_url: limits.billing_url,
    };
  },
});
