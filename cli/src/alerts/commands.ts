/** `pinecall monitors | webhook | telemetry`: what the org watches, where its alerts go, where its traces go. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { UsageError } from "../errors.js";
import { secretReader } from "../kit/stdin.js";
import * as render from "./render.js";
import * as service from "./service.js";
import { repeated } from "../kit/flags.js";

const MONITORS = `
A monitor watches one number of the observability series over a window of days, for every agent
or one, and fires — once a day, as monitor.fired on the agent's log, where the console and
\`sessions\` show it — the first seal of a call that finds it on the wrong side of the line:

  e2e_median_s       the caller's wait from their last word to the agent's first, median, seconds
  llm_median_s       the model's time to its first token, median, seconds
  held_rate          the share of the judges' verdicts that held, 0 to 1 (--below)
  escalated_rate     the share of calls a person took over, 0 to 1
  tool_failure_rate  the share of tool calls that failed, 0 to 1
  spend_usd          what the calls cost, dollars
  calls              how many calls there were

--above fires when the number is over the line, --below when it is under; --days is the window
(7 when left out). The list says, per monitor, the last day it fired and the value that crossed.

Examples
  $ pinecall monitors add "slow answers" --metric e2e_median_s --above 2 --days 7
  $ pinecall monitors add "judges slipping" --metric held_rate --below 0.9 --agent front-desk
  $ pinecall monitors
  $ pinecall monitors rm mon_8b1d2e3f4a5c
`;

const WEBHOOK = `
Every alert of the org — a monitor that fired (monitor.fired), today's spend three times the
usual (spend.unusual), a quota that ran out (credits.exhausted) — is written on the agent's log
and, with a webhook set, posted there too as JSON; a hosted app that went down (app.failed) is
no agent's, so it is posted alone, with agent null. The post is {type, org, env, agent, at, data}, with
x-pinecall-event naming the type. Tried twice within five seconds; a URL that fails is logged
and the log keeps the alert.

set takes the URL on the command line and, with --secret, the secret from stdin — typed with
nothing echoed on a terminal, or piped — never from a flag. With a secret every post carries
x-pinecall-signature: sha256=<HMAC-SHA256 of the body>. The gateway keeps the secret sealed and
never reads it back. test posts one webhook.test event and says whether the URL answered 2xx.

Examples
  $ printf %s "$WEBHOOK_SECRET" | pinecall webhook set https://hooks.example.com/pinecall --secret
  $ pinecall webhook test
`;

const TELEMETRY = `
A copy of every spoken call's spans — the model's requests, speech in and out, every tool the
agent ran — goes over OTLP to the collector named here: Langfuse, Datadog, Grafana, or one of
yours. Off until set; a chat has no worker and so no spans.

set takes the collector's URL on the command line and each header's VALUE from stdin, one per
--header, in the order named — typed with nothing echoed on a terminal, or piped one line per
header — never from a flag. --pii lets a span carry what was said and what a tool got; without
it the words are stripped before export. The gateway keeps the headers sealed.

Examples
  $ printf %s "$DD_API_KEY" | pinecall telemetry set https://otlp.datadoghq.eu/v1/traces --header dd-api-key
  $ printf 'Basic %s\\n4\\n' "$CREDS" | pinecall telemetry set https://cloud.langfuse.com/api/public/otel/v1/traces \\
      --header Authorization --header x-langfuse-ingestion-version
`;

export function register(program: Command, ctx: Context): void {
  const monitors = program
    .command("monitors")
    .description("the numbers this org watches — latency, the judges, escalations, tools, spend — and the line each must not cross")
    .addHelpText("after", MONITORS);
  monitors
    .command("list", { isDefault: true })
    .description("what this org watches, and when each monitor last fired")
    .action(async () => ctx.io.result(await service.listMonitors(ctx), render.monitors));
  monitors
    .command("add")
    .description("watch a number: fires when it crosses the line")
    .argument("<name>", "the monitor's name, as the alert will read")
    .requiredOption("--metric <metric>", `one of ${service.METRICS.join(", ")}`)
    .option("--above <n>", "fire when the number is over the line")
    .option("--below <n>", "fire when the number is under the line")
    .option("--days <days>", "the window: 1, 7 or 30", "7")
    .option("--agent <name>", "one agent's calls alone; every agent's when left out")
    .action(async (name, flags) => {
      if ((flags.above === undefined) === (flags.below === undefined)) throw new UsageError("the line is --above <n> or --below <n>, one of them");
      const input = service.AddMonitorInput.parse({
        name,
        metric: flags.metric,
        above: flags.above !== undefined,
        threshold: Number(flags.above ?? flags.below),
        windowDays: Number(flags.days),
        agent: flags.agent,
      });
      ctx.io.result(await service.addMonitor(ctx, input), render.monitor);
    });
  monitors
    .command("rm")
    .description("forget a monitor")
    .argument("<id>", "the monitor's id, as the list shows it")
    .action(async (id) => ctx.io.result(await service.removeMonitor(ctx, id), render.monitorRemoved));

  const webhook = program
    .command("webhook")
    .description("where this org's alerts are posted: a webhook of its own, set with a secret, proven with a test, cleared")
    .addHelpText("after", WEBHOOK);
  webhook
    .command("show", { isDefault: true })
    .description("the URL, and whether posts are signed")
    .action(async () => ctx.io.result(await service.getWebhook(ctx), render.webhook));
  webhook
    .command("set")
    .description("a URL of yours; the secret, if any, on stdin")
    .argument("<url>")
    .option("--secret", "read a signing secret from stdin")
    .action(async (url, flags) => {
      const secret = flags.secret === true ? await secretReader(ctx.io)("secret") : null;
      if (secret === "") throw new UsageError("--secret: an empty secret; pipe it, or type it when asked");
      ctx.io.result(await service.setWebhook(ctx, service.SetWebhookInput.parse({ url, secret })), render.webhook);
    });
  webhook
    .command("test")
    .description("one signed test post, waited for")
    .action(async () => ctx.io.result(await service.testWebhook(ctx), render.webhookTested));
  webhook
    .command("clear")
    .description("stop the posting")
    .action(async () => ctx.io.result(await service.clearWebhook(ctx), render.webhookCleared));

  const telemetry = program
    .command("telemetry")
    .description("where this org's calls' traces go: its own OpenTelemetry collector, set, read and taken back")
    .addHelpText("after", TELEMETRY);
  telemetry
    .command("show", { isDefault: true })
    .description("the collector, the headers' names, whether words travel")
    .action(async () => ctx.io.result(await service.getCollector(ctx), render.collector));
  telemetry
    .command("set")
    .description("an OTLP collector; each header's value on stdin")
    .argument("<url>")
    .option("--header <name>", "a header to send, its value read from stdin; again for another, one line each, in order", repeated)
    .option("--pii", "let a span carry what was said and what a tool got")
    .action(async (endpoint, flags) => {
      const read = secretReader(ctx.io);
      const headers: Record<string, string> = {};
      for (const name of flags.header ?? []) {
        const value = await read(name);
        if (value === "") throw new UsageError(`header ${name}: an empty value; pipe it, or type it when asked`);
        headers[name] = value;
      }
      const input = service.SetCollectorInput.parse({ endpoint, headers, pii: flags.pii === true });
      ctx.io.result(await service.setCollector(ctx, input), render.collector);
    });
  telemetry
    .command("clear")
    .description("stop the export")
    .action(async () => ctx.io.result(await service.clearCollector(ctx), render.collectorCleared));
}
