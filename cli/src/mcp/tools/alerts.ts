/** The `monitors`, `webhook`, `alerts` and `telemetry` tools: the alerts domain, over its service. */

import { z } from "zod";

import * as render from "../../alerts/render.js";
import * as service from "../../alerts/service.js";
import { tool, ToolRefused } from "../tool.js";

export const monitors = tool({
  name: "monitors",
  description: "The numbers the org watches over a window — latency, the judges' held rate, escalations, tool failures, spend, calls — and the line each must not cross; list them, add one, forget one.",
  schema: {
    action: z.enum(["list", "add", "rm"]).describe("list says every monitor with the last day it fired; add watches a number; rm forgets one by id"),
    ...service.AddMonitorInput.partial().shape,
    id: z.string().optional().describe("rm: the monitor's id, from list"),
  },
  manual:
    "`monitors list` says what the org watches in the env — each monitor's rule, who set it, the last day it fired and the value that crossed. `add` watches one number of the observability series (the same the console's Observability screen draws) over 1, 7 or 30 days, for every agent or one, and fires once a day as `monitor.fired` on the agent's log the first time a call's seal finds it on the wrong side of the line. `rm` forgets one. Use it when the person asks to be told when latency, the judges, escalations, tool failures, spend or volume slip.",
  handler: async (args, ctx) => {
    if (args.action === "rm") {
      if (args.id === undefined) throw new ToolRefused("rm names the monitor's id");
      return await service.removeMonitor(ctx, args.id);
    }
    if (args.action === "add") {
      const parsed = service.AddMonitorInput.safeParse(args);
      if (!parsed.success) throw new ToolRefused("add names the monitor, its metric, whether it fires above or below, and the threshold");
      const added = await service.addMonitor(ctx, parsed.data);
      return { monitor: added, says: render.monitor(added) };
    }
    return { monitors: await service.listMonitors(ctx) };
  },
});

export const webhook = tool({
  name: "webhook",
  description: "Where the org posts its alerts — a monitor fired, the spend unusual, a quota out — shown, proven with a test post (signed when it has a secret), or cleared. Setting one is the person's, in a terminal: the secret is a credential.",
  schema: {
    action: z.enum(["show", "test", "clear"]).describe("show says the URL and whether posts are signed; test posts one webhook.test event and says whether the URL answered 2xx; clear stops the posting"),
  },
  manual:
    "`webhook` reads where this org's alerts are posted beyond the agent's log ({type, org, env, agent, at, data}, with x-pinecall-event and, when a secret is set, x-pinecall-signature as sha256=<HMAC-SHA256 of the body>), proves the URL with a test post, and can stop it. Pointing it somewhere is never a tool, since the secret is a credential: the person types `pinecall webhook set <url> --secret` in a terminal, where the secret is read off stdin.",
  handler: async (args, ctx) => {
    if (args.action === "clear") return await service.clearWebhook(ctx);
    if (args.action === "test") return await service.testWebhook(ctx);
    const found = await service.getWebhook(ctx);
    return found === null ? { webhook: null, says: render.NO_WEBHOOK } : { webhook: found };
  },
});

export const alerts = tool({
  name: "alerts",
  description: "What the org was told in the environment, newest first: every alert kept — a monitor fired, the spend unusual, a quota out, a hosted app down — whether or not a webhook is set, and whether each was mailed.",
  schema: {
    limit: z.number().int().min(1).max(200).optional().describe("how many, newest first; 50 when left out, 200 at most"),
  },
  manual:
    "`alerts` reads what this org was told in the env (`prod` for production's): each alert's kind (`monitor.fired`, `spend.unusual`, `credits.exhausted`, `app.failed`), its agent, its data — the monitor and the value that crossed, the app, the quota — when it was raised, and whether it was mailed to the org's admins. Kept 90 days whether or not a webhook is set. Read it when the person asks what went wrong lately, or whether a monitor fired; `monitors` says what is watched, `webhook` where alerts are posted.",
  handler: async (args, ctx) => ({ alerts: await service.listAlerts(ctx, args.limit ?? 50) }),
});

export const telemetry = tool({
  name: "telemetry",
  description: "Where the org's calls' traces go — its own OpenTelemetry collector — shown or cleared. Setting one is the person's, in a terminal: a header's value is a credential.",
  schema: {
    action: z.enum(["show", "clear"]).describe("show says the collector, the headers' names and whether words travel; clear stops the export"),
  },
  manual:
    "`telemetry` reads where a copy of every spoken call's spans goes over OTLP, and can stop it. Pointing it at a collector is never a tool, since a header's value is a credential: the person types `pinecall telemetry set <url> --header <name>` in a terminal, where each value is read off stdin.",
  handler: async (args, ctx) => {
    if (args.action === "clear") return await service.clearCollector(ctx);
    const found = await service.getCollector(ctx);
    return found === null ? { collector: null, says: render.NO_COLLECTOR } : { collector: found };
  },
});
