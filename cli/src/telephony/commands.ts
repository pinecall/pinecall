/** `pinecall numbers | carriers | line | callbacks`: the org's numbers and accounts, whose terminal a ring lands in, who to call back. */

import type { Command } from "@commander-js/extra-typings";

import { connectionLine, type Context } from "../context.js";
import { GatewayError, UsageError } from "../errors.js";
import { secretReader } from "../kit/stdin.js";
import * as render from "./render.js";
import * as service from "./service.js";

const NUMBERS = `
A number is one env's and reaches one agent: it is imported where it answers, and \`list\` shows
that env's — the sandbox's, or production's with --prod. No verb here moves a number between the
two; the console's Numbers screen does.

\`available\` is every number the org's Twilio accounts own, and whether this env routes it.
\`import\` takes a number the org's carrier account already owns and points it here — \`--dry-run\`
prints the steps and writes nothing. An org with several accounts names the one that owns the
number with \`--account\` (\`pinecall carriers list\` shows them). \`drop\` forgets the route and
takes the number off the SFU trunk; the carrier account keeps it.

\`buy\` is for an org with no number of its own: the deployment buys one in the country (and
area code) on its own account and points it at the agent. A bought number counts against the
org's \`numbers\` limit in that env (\`pinecall limits\`); an imported one never does.

Examples
  $ pinecall numbers import +34910000000 --agent clinica-norte
  $ pinecall numbers buy --country ES --area 91 --agent clinica-norte --dry-run --prod
  $ pinecall numbers available --prod
`;

const CARRIERS = `
An account is where the org's numbers live: a Twilio account, a SIP peer (its own PBX or a
carrier with no API here), a WhatsApp number at Meta. It is the org's, one for both envs, and
\`pinecall numbers import\` then routes a number it owns to an agent.

Every secret is read on stdin and never from the command line: typed with nothing echoed on a
terminal, or piped one per line — a SIP peer's password, then its outbound password when
--outbound-username is given. \`add\` with an account the org already holds replaces its secret.
A peer's networks wait for Pinecall's operator before 5060 opens to them; \`show\` says where each
one stands. \`drop\` forgets an account and leaves its numbers routed until each is dropped.

Examples
  $ pinecall carriers add twilio --account-sid AC0123… --user SK4567… --label Clínica
`;

const LINE = `
With nothing after it: who is answering this agent's number right now, and who else is running
it and could take it.

\`from <+number>\` says which phone is YOURS, once, and every call you make reaches your own
agent — while you are running the agent your phone reaches your copy, and everybody else
reaches production. It is kept in ~/.pinecall/session.json under the gateway's URL, and re-sent
by every \`pinecall start\`. \`forget\` undoes it.

\`claim\` and \`release\` are the fallback, for a call from a number nobody said was theirs. The
first terminal to hold the agent has it.

Examples
  $ pinecall line from +59899111111
  calls from +59899111111 reach this terminal
  $ pinecall line
  rings in berna@clinica.test · \`pinecall line from <+your-number>\` routes yours, or \`claim\` takes it
`;

const CALLBACKS = `
Every callback.requested this org's agents wrote — a phone caller the overflow agent answered,
one the agent's own tool promised a call back, or a web visitor who left a number at the widget
— oldest first, with the cursor the next page starts at. The runtime records them; dialing back
is your app's.
`;

export function register(program: Command, ctx: Context): void {
  const numbers = program.command("numbers").description("list | available | import | buy | drop the numbers the org answers at").addHelpText("after", NUMBERS);
  numbers
    .command("list", { isDefault: true })
    .description("every number of this env, and the agent each reaches")
    .action(async () => ctx.io.result(await service.listNumbers(ctx), render.numbers));
  numbers
    .command("available")
    .description("what the org's Twilio accounts own, and whether this env routes it")
    .option("--account <id>", "one account of several")
    .action(async (flags) => ctx.io.result(await service.listAvailableNumbers(ctx, flags.account), render.available));
  numbers
    .command("import")
    .description("a number the org's carrier account owns, pointed at an agent")
    .argument("<number>", "+E.164")
    .requiredOption("--agent <slug>")
    .option("--account <id>", "the account that owns it, when the org has several")
    .option("--channel <channel>", "phone | whatsapp")
    .option("--dry-run", "print the steps and write nothing")
    .action(async (number, flags) =>
      withAccountHint(async () => {
        const input = service.ImportNumberInput.parse({ number, agent: flags.agent, account: flags.account, channel: flags.channel, dryRun: flags.dryRun === true });
        ctx.io.result(await service.importNumber(ctx, input), render.imported);
      }),
    );
  numbers
    .command("buy")
    .description("a number bought on the deployment's own account, pointed at an agent")
    .requiredOption("--country <XX>", "two letters")
    .option("--area <digits>", "an area code")
    .requiredOption("--agent <slug>")
    .option("--channel <channel>", "phone | whatsapp")
    .option("--dry-run", "name the number and buy nothing")
    .action(async (flags) => {
      const input = service.BuyNumberInput.parse({ country: flags.country, agent: flags.agent, areaCode: flags.area, channel: flags.channel, dryRun: flags.dryRun === true });
      ctx.io.result(await service.buyNumber(ctx, input), render.bought);
    });
  numbers
    .command("drop")
    .description("forget the route; the carrier account keeps the number")
    .argument("<number>")
    .action(async (number) => ctx.io.result(await service.dropNumber(ctx, number), render.dropped));

  const carriers = program.command("carriers").description("list | show | add | drop the org's carrier accounts: Twilio, a SIP peer, WhatsApp").addHelpText("after", CARRIERS);
  carriers
    .command("list", { isDefault: true })
    .description("every carrier account of the org, oldest first")
    .action(async () => ctx.io.result(await service.listCarriers(ctx), render.carriers));
  carriers
    .command("show")
    .description("one account, named, never its secret")
    .argument("[account]", "the org's only one when left out")
    .action(async (account) => ctx.io.result(await service.showCarrier(ctx, account), render.carrier));
  const add = carriers.command("add").description("keep an account: its fields from the flags, its secrets from stdin");
  add
    .command("twilio")
    .description("a Twilio account: its SID, an API key and its secret on stdin")
    .requiredOption("--account-sid <AC…>")
    .requiredOption("--user <SK…>", "an API key SID, or the account SID again")
    .option("--label <name>")
    .action(async (flags) => addCarrier({ kind: "twilio", accountSid: flags.accountSid, user: flags.user, label: flags.label }));
  add
    .command("sip")
    .description("a SIP peer: who calls from where, and how calls go out; the password on stdin")
    .requiredOption("--username <user>")
    .requiredOption("--address <ip or network...>", "the networks it calls from")
    .option("--outbound-host <host>")
    .option("--outbound-transport <auto|udp|tcp|tls>")
    .option("--outbound-username <user>")
    .option("--label <name>")
    .action(async (flags) =>
      addCarrier({
        kind: "sip",
        username: flags.username,
        addresses: flags.address,
        outboundHost: flags.outboundHost,
        outboundTransport: flags.outboundTransport,
        outboundUsername: flags.outboundUsername,
        label: flags.label,
      }),
    );
  add
    .command("whatsapp")
    .description("a WhatsApp Business number: its id, and Meta's token on stdin")
    .requiredOption("--phone-number-id <id>")
    .option("--label <name>")
    .action(async (flags) => addCarrier({ kind: "whatsapp", phoneNumberId: flags.phoneNumberId, label: flags.label }));
  carriers
    .command("drop")
    .description("an account let go; its numbers stop ringing here")
    .argument("[account]")
    .action(async (account) => ctx.io.result(await service.dropCarrier(ctx, account), render.carrierDropped));

  const line = program.command("line").description("which phone is yours, and whose terminal anybody else's call rings in").addHelpText("after", LINE);
  line
    .command("show", { isDefault: true })
    .description("where the agent's line rings, and whose phones reach this terminal")
    .argument("[agent.tsx]")
    .option("--agent <name>")
    .action(async (file, flags) => ctx.io.result(await service.showLine(ctx, { file, agent: flags.agent }), render.line));
  line
    .command("from")
    .description("which phone is yours: its calls reach your own agent")
    .argument("<number>", "+E.164")
    .action(async (number) => ctx.io.result(await service.setCallerNumber(ctx, number), render.calling));
  line
    .command("forget")
    .description("your phone no longer routed to you")
    .action(async () => ctx.io.result(await service.forgetCallerNumber(ctx), render.callerForgotten));
  line
    .command("claim")
    .description("take the line for this terminal")
    .argument("[agent.tsx]")
    .option("--agent <name>")
    .action(async (file, flags) => ctx.io.result(await service.claimLine(ctx, { file, agent: flags.agent }), render.line));
  line
    .command("release")
    .description("give the line to another terminal running the agent")
    .argument("[agent.tsx]")
    .option("--agent <name>")
    .action(async (file, flags) => ctx.io.result(await service.releaseLine(ctx, { file, agent: flags.agent }), render.released));

  program
    .command("callbacks")
    .description("the numbers people left when every seat was taken: who to call back")
    .option("--agent <slug>")
    .option("--after <cursor>")
    .addHelpText("after", CALLBACKS)
    .action(async (flags) => {
      const after = flags.after === undefined ? undefined : Number(flags.after);
      if (after !== undefined && !Number.isInteger(after)) throw new UsageError(`--after takes the cursor the page before answered, not ${flags.after}`);
      ctx.io.info(connectionLine(ctx));
      ctx.io.result(await service.listCallbacks(ctx, service.ListCallbacksInput.parse({ agent: flags.agent, after })), render.callbacks);
    });

  // The secrets: one silent prompt each on a terminal, else one line of stdin each, in order.
  async function addCarrier(wanted: unknown): Promise<void> {
    const input = service.AddCarrierInput.parse(wanted);
    const read = secretReader(ctx.io);
    const secrets: Record<string, string> = {};
    for (const [name, field] of service.secretsOf(input)) secrets[field] = await read(name);
    ctx.io.result(await service.addCarrier(ctx, input, secrets), render.carrierKept);
  }

  // The gateway's 409 when the org holds several accounts: the hint names the flag.
  async function withAccountHint(run: () => Promise<void>): Promise<void> {
    try {
      await run();
    } catch (failed) {
      if (failed instanceof GatewayError && failed.status === 409 && failed.message.includes(service.SEVERAL_ACCOUNTS)) ctx.io.info(service.NAME_THE_ACCOUNT);
      throw failed;
    }
  }
}
