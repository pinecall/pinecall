/** `pinecall judges | judging`: every judge a call meets, one tried on calls, and whether the org's calls are judged and on what. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { GatewayError, UsageError } from "../errors.js";
import { listOf } from "../kit/flags.js";
import { parseKeyValues } from "../kit/keyvalue.js";
import * as render from "./render.js";
import * as service from "./service.js";

const JUDGES = `
Every judge is one question a model answers about a finished call, with the whole call in front
of it — the turns, the tool calls, the positions it cites. Three lists, in the order a call meets
them: PINECALL's library (consent, grounded, promises, disclosed, identified, honoured-stop,
ended-well, expected-outcome, relevance, repetition, sentiment; every one off until switched on),
switched on or off for the org (--org) or for one agent, the agent's switch winning; the ORG's
own, asked of every agent's calls; and one AGENT's own, about its job alone.

A judge answers a verdict (held or broken), a score from 1 to 5, or one of its choices; any of
them may answer N/A — the question did not apply, never billed. It runs on every call, only on a
simulated one, or on a trigger: a yes-or-no asked first, and a no is N/A. Each judge that answers
is one eval; on a model of your org's own key (\`pinecall judging --model\`) evals are not billed.

Examples
  $ pinecall judges add offers-next-slot --asks "The agent offered the next free slot before the caller asked twice."
  offers-next-slot written · 12 judge(s)
  $ pinecall judges off relevance --org
  relevance off · 12 judge(s)
  $ pinecall judges try offers-next-slot --last 3
  CA_8f4a2c  ✓ held  Offered Thursday at 09:30 unasked.  [seq 14]
  3 evals · $0.0031 · nothing was written
`;

const JUDGING = `
Every finished call of the org is judged at hang-up unless judging is off. The judges run on
Pinecall's judge model, and each judge that answers is one eval on your bill — unless you name a
model of your own: --model is the model every agent's calls are judged on (an agent's own
\`pinecall agent set --judge\` wins over it), tried on your org's keys before it is kept. On your
org's own key for its vendor (\`pinecall providers add\`) the model's bill is yours and its evals
are never billed; a local model is your vendor's plugin pointed at your server, --option
base_url=… --platform goes back to Pinecall's model.

Examples
  $ pinecall judging
  judging on · Pinecall's judge model · evals billed · ceiling $0.05 a call
  $ pinecall judging --model openai/qwen3-32b --option base_url=http://gpu.internal:8000/v1
  $ pinecall judging off
`;

export function register(program: Command, ctx: Context): void {
  const judges = program
    .command("judges")
    .description("every judge a call meets: Pinecall's, switched on or off; the org's own and the agent's own; one tried on calls")
    .addHelpText("after", JUDGES);
  const owner = (flags: { org?: boolean | undefined; agent?: string | undefined }): service.JudgeOwner =>
    service.ownerOf(ctx, service.OwnerInput.parse({ org: flags.org === true, agent: flags.agent }));
  judges
    .command("list", { isDefault: true })
    .description("every judge the list meets: whose, on or off, how it answers, when it runs")
    .option("--org", "the org's list")
    .option("--agent <name>", "one agent's, when the project holds more")
    .action(async (flags) => {
      const whose = owner(flags);
      ctx.io.result(await service.listJudges(ctx, whose), (list) => render.judges(whose, list));
    });
  judges
    .command("add")
    .description("write one of your own; the same name again replaces it")
    .argument("<name>")
    .requiredOption("--asks <question>", "one question about the whole call")
    .option("--answer <how>", "verdict (the default) · score · choice:a,b,c")
    .option("--when <when>", "always (the default) · simulations · trigger:'…'")
    .option("--reads <what>", `any of ${service.READS.join(", ")}, comma-separated`)
    .option("--org")
    .option("--agent <name>")
    .action(async (name, flags) => withHint("add", name, async () => ctx.io.result(await service.addJudge(ctx, owner(flags), name, service.JudgeFlags.parse(flags)), render.changed)));
  for (const verb of ["on", "off"] as const) {
    judges
      .command(verb)
      .description(`one of Pinecall's judges switched ${verb} for the org (--org) or the agent`)
      .argument("<name>")
      .option("--org")
      .option("--agent <name>")
      .action(async (name, flags) => withHint(verb, name, async () => ctx.io.result(await service.switchJudge(ctx, owner(flags), name, verb === "on"), render.changed)));
  }
  judges
    .command("rm")
    .description("one of your own dropped; Pinecall's are never dropped, only switched off")
    .argument("<name>")
    .option("--org")
    .option("--agent <name>")
    .action(async (name, flags) => withHint("rm", name, async () => ctx.io.result(await service.removeJudge(ctx, owner(flags), name), render.changed)));
  judges
    .command("try")
    .description("ask one judge of finished calls and write nothing")
    .argument("<name>")
    .option("--last <n>", "the agent's newest n finished calls (1 to 50)")
    .option("--calls <ids>", "the calls named, comma-separated")
    .option("--asks <question>", "a judge not yet saved, written whole with add's flags")
    .option("--answer <how>")
    .option("--when <when>")
    .option("--reads <what>")
    .option("--org")
    .option("--agent <name>")
    .action(async (name, flags) => {
      if (flags.org === true) throw new UsageError(service.TRY_IS_AN_AGENTS);
      const last = flags.last === undefined ? undefined : Number(flags.last);
      if (last !== undefined && !Number.isInteger(last)) throw new UsageError(`--last ${flags.last} is not 1 to 50 calls`);
      const calls = listOf(flags.calls);
      const input = service.TryJudgeInput.parse({ name, asks: flags.asks, answer: flags.answer, when: flags.when, reads: flags.reads, agent: flags.agent, last, calls });
      ctx.io.result(await service.tryJudge(ctx, input), render.tried);
    });

  // One verb: alone it reads; with on|off or a model it writes, and answers what stands after.
  program
    .command("judging")
    .description("whether this org's calls are judged at hang-up, and the model the judges run on: Pinecall's, or one of yours")
    .argument("[on|off]", "judging on or off for every agent, from the next call; the model is kept")
    .option("--model <vendor/model>", "a model of yours, or haiku · sonnet · opus")
    .option("--option <key=value...>", "one keyword argument of the model's plugin; the value read as JSON")
    .option("--platform", "Pinecall's judge model again")
    .addHelpText("after", JUDGING)
    .action(async (verb, flags) => {
      if (verb !== undefined && verb !== "on" && verb !== "off") throw new UsageError(`judging takes on or off, not ${verb}`);
      const input = service.SetJudgingInput.parse({
        on: verb === undefined ? undefined : verb === "on",
        model: flags.model,
        options: parseKeyValues("option", flags.option),
        platform: flags.platform === true,
      });
      ctx.io.result(await service.setJudging(ctx, input), render.judging);
    });

  // A 409 names the CLI's own verb for what was asked of the wrong list.
  async function withHint(verb: string, name: string, run: () => Promise<void>): Promise<void> {
    try {
      await run();
    } catch (failed) {
      const hint = failed instanceof GatewayError && failed.status === 409 ? render.hintFor(verb, name) : undefined;
      if (hint !== undefined) ctx.io.info(hint);
      throw failed;
    }
  }
}
