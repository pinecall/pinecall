/** `pinecall numbers | carriers | line | callbacks`: the org's numbers and accounts, whose terminal a ring lands in, who to call back. */

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import { GatewayError, UsageError } from "../errors.js";
import { repeated } from "../kit/flags.js";
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

\`address\` gives an agent an address of the deployment's own domain, as \`buy\` gives it a number:
\`<word>.<org>@<domain>\`, its mailbox made on the deployment's mail host and routed; with \`--app\` its
emails go to that app's flows. \`drop\` lets it go, and its mailbox with it.

Examples
  $ pinecall numbers import +34910000000 --agent clinica-norte
  $ pinecall numbers buy --country ES --area 91 --agent clinica-norte --dry-run --prod
  $ pinecall numbers available --prod
  $ pinecall numbers address avisos --agent front-desk --app front-desk
`;

const CARRIERS = `
An account is where the org's numbers live: a Twilio account, a SIP peer (its own PBX or a
carrier with no API here), a WhatsApp number at Meta, a Facebook Page (its Messenger, and the
Instagram account linked to it), a mailbox. It is the org's, one for both envs, and
\`pinecall numbers import\` then routes a number it owns to an agent: a Page by its id on
--channel messenger, its Instagram account by that account's id on --channel instagram.

Every secret is read on stdin and never from the command line: typed with nothing echoed on a
terminal, or piped one per line — a SIP peer's password, then its outbound password when
--outbound-username is given. \`add\` with an account the org already holds replaces its secret.
A peer's networks wait for Pinecall's operator before 5060 opens to them; \`show\` says where each
one stands. \`drop\` forgets an account and leaves its numbers routed until each is dropped.

Examples
  $ pinecall carriers add twilio --account-sid AC0123… --user SK4567… --label Clínica
  $ pinecall carriers add messenger --page-id 1472943555898656 --instagram-id 17841400000000001
`;

const LINE = `
With nothing after it: who is answering this agent's number right now, and who else is running
it and could take it.

\`from <+number>\` says which phone is YOURS, once. A call from it to the box's test number, which
the answer names, reaches your org's sandbox agent — the one \`--agent\` names, or the one the org
holds — in your own copy while \`pinecall start\` holds one, else in the org's own; a call from it to
a production number does the same, while everybody else reaches production. It is kept in
~/.pinecall/session.json under the gateway's URL, and re-sent by every \`pinecall start\`.
\`forget\` undoes it.

\`claim\` and \`release\` are the fallback, for a call from a number nobody said was theirs. The
first terminal to hold the agent has it.

Examples
  $ pinecall line from +59899111111
  calls from +59899111111 reach your copy of the agent you hold · dial +13617334133 to hear it
  $ pinecall line
  rings in berna@clinica.test · \`pinecall line from <+your-number>\` routes yours, or \`claim\` takes it
`;

const DIAL = `
The agent calls the number, from one of its own, and the call opens with what you hand it:

  $ pinecall dial reminder +14155550142 --state '{"visit": "v-812"}'
  $ pinecall dial reminder +14155550142 --instruction "Remind Ana of her cleaning tomorrow at 9:30 and ask her to confirm."

--greeting is the words the call opens with, over the agent's own greeting. --instruction is what
the call is for: the agent reads it for the whole call and, with no greeting, opens on it.

Somebody must be holding the agent. Every dial passes the org's guards first (who may be called,
when, how often); one that is refused rings nobody and says which guard refused it.
`;

const TEMPLATE = `
A template is the one message WhatsApp lets a business open a conversation with, and the one Meta
charges for, on the account of whoever owns the number. The agent sends it from the number it
answers WhatsApp at, its body's {{1}}, {{2}}… filled by each --var in order:

  $ pinecall template reminder visit_reminder --to +14155550142 --language en_US --var Ana --var "tomorrow at 9:30" --prod

With --text, the words the template says, they are the first turn of the contact's conversation: what
they answer reaches the agent with those words before it, and the console shows them. Somebody must be
holding the agent then.

  $ pinecall template reminder visit_reminder --to +14155550142 --language en_US --var Ana --text "Hi Ana, your cleaning is tomorrow at 9:30. Reply here to change it." --prod

In the sandbox nothing is sent: the answer says what would have gone, marked simulated, and the
agent needs no WhatsApp number there. A contact who asked for no more messages is written to by nobody.
`;

const TEXT = `
The agent sends the contact one SMS, from a number it answers SMS at, and what they answer reaches it:

  $ pinecall text reminder +14155550142 "Ana, your cleaning is tomorrow at 9:30. Reply here to change it."

To an address, the agent writes the first email of a thread, from an address it answers email at,
under --subject; the contact's reply lands on the same conversation. With no words, the agent writes
the email itself, on --instruction, as a dialled call with no greeting opens:

  $ pinecall text reminder ana@example.org "Your cleaning is tomorrow at 9:30." --subject "Your visit"
  $ pinecall text reminder ana@example.org --subject "Your visit" --instruction "Remind Ana of her cleaning." --metadata '{"visit": "v-812"}'

Somebody must be holding the agent. A contact whose conversation is still open is written on it.
Any other passes the org's guards first, as a dial does (who may be reached, when, how often), and
one that is refused is sent nothing. A contact who texted STOP is written to by nobody.
`;

// A flag that takes JSON takes an object: the state a call opens in, what its call.started carries.
function jsonOf(flag: string, given: string | undefined): Record<string, unknown> | undefined {
  if (given === undefined) return undefined;
  try {
    const parsed: unknown = JSON.parse(given);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
  } catch {
    // Said below, with the flag's name.
  }
  throw new UsageError(`${flag} takes a JSON object, like '{"visit": "v-812"}'`);
}

const CALLBACKS = `
Every callback.requested this org's agents wrote — a phone caller the overflow agent answered,
one the agent's own tool promised a call back, or a web visitor who left a number at the widget
— oldest first, with the cursor the next page starts at. The runtime records them; dialing back
is your app's.
`;

export function register(program: Command, ctx: Context): void {
  const numbers = program.command("numbers").description("list | available | import | buy | address | drop the numbers the org answers at").addHelpText("after", NUMBERS);
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
    .argument("<number>", "+E.164; an address for email; Meta's id of a Page or an Instagram account")
    .requiredOption("--agent <slug>")
    .option("--account <id>", "the account that owns it, when the org has several")
    .option("--channel <channel>", "phone | whatsapp | sms | email | messenger | instagram")
    .option("--move", "take the number off the trunk it is on now, when it answers in another environment or for another agent")
    .option("--app <name>", "an address alone: its emails go to this app's flows as mail.received, and open no conversation")
    .option("--dry-run", "print the steps and write nothing")
    .action(async (number, flags) =>
      withAccountHint(async () => {
        const input = service.ImportNumberInput.parse({ number, agent: flags.agent, account: flags.account, channel: flags.channel, move: flags.move === true, app: flags.app, dryRun: flags.dryRun === true });
        ctx.io.result(await service.importNumber(ctx, input), render.imported);
      }),
    );
  numbers
    .command("buy")
    .description("a number bought on the deployment's own account, pointed at an agent")
    .requiredOption("--country <XX>", "two letters")
    .option("--area <digits>", "an area code")
    .requiredOption("--agent <slug>")
    .option("--channel <channel>", "phone | whatsapp | sms | email")
    .option("--dry-run", "name the number and buy nothing")
    .action(async (flags) => {
      const input = service.BuyNumberInput.parse({ country: flags.country, agent: flags.agent, areaCode: flags.area, channel: flags.channel, dryRun: flags.dryRun === true });
      ctx.io.result(await service.buyNumber(ctx, input), render.bought);
    });
  numbers
    .command("address")
    .description("an address of the deployment's own domain for an agent: <word>.<org>@<domain>, its mailbox made and routed")
    .argument("<word>", "lowercase letters, digits and dashes: avisos")
    .requiredOption("--agent <slug>")
    .option("--app <name>", "its emails go to this app's flows as mail.received, and open no conversation")
    .option("--label <name>", "the name a contact reads beside the address")
    .action(async (word, flags) => {
      const input = service.AddressInput.parse({ local: word, agent: flags.agent, app: flags.app, label: flags.label });
      ctx.io.result(await service.giveAddress(ctx, input), render.imported);
    });
  numbers
    .command("drop")
    .description("forget the route; the carrier account keeps the number")
    .argument("<number>")
    .option("--channel <channel>", "phone | whatsapp | sms | email | messenger | instagram: the one to let go, for a number on several")
    .action(async (number, flags) => {
      try {
        ctx.io.result(await service.dropNumber(ctx, number, service.DropChannel.parse(flags.channel)), render.dropped);
      } catch (failed) {
        // The gateway's 409 for a number that answers on two channels: the hint names the flag.
        if (failed instanceof GatewayError && failed.status === 409 && failed.message.includes(service.ON_SEVERAL_CHANNELS)) ctx.io.info(service.NAME_THE_CHANNEL);
        throw failed;
      }
    });

  const carriers = program.command("carriers").description("list | show | add | drop the org's carrier accounts: Twilio, a SIP peer, WhatsApp, a Facebook Page, a mailbox").addHelpText("after", CARRIERS);
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
    .description("a WhatsApp Business number: its id, then Meta's token and your Meta app's secret on stdin")
    .requiredOption("--phone-number-id <id>")
    .option("--label <name>")
    .action(async (flags) => addCarrier({ kind: "whatsapp", phoneNumberId: flags.phoneNumberId, label: flags.label }));
  add
    .command("messenger")
    .description("a Facebook Page, for its Messenger and its Instagram account: its id, then a Page token and your Meta app's secret on stdin")
    .requiredOption("--page-id <id>")
    .option("--instagram-id <id>", "the Instagram account linked to the Page, when the token cannot read it from the Page")
    .option("--label <name>")
    .action(async (flags) => addCarrier({ kind: "messenger", pageId: flags.pageId, instagramId: flags.instagramId, label: flags.label }));
  add
    .command("email")
    .description("a mailbox: IMAP to read it, SMTP to answer from it; its password on stdin, then a relay's")
    .requiredOption("--address <address>", "the mailbox's address")
    .requiredOption("--imap-host <host>", "where it is read, over TLS")
    .requiredOption("--smtp-host <host>", "where its replies leave: its own server, or a relay such as Amazon SES")
    .option("--imap-port <port>", "993 when left out")
    .option("--smtp-port <port>", "465 (TLS) when left out; 587 is STARTTLS")
    .option("--username <login>", "the IMAP login, when it is not the address")
    .option("--smtp-username <login>", "a relay's own login; its password is asked after the mailbox's")
    .option("--name <name>", "the name the contact reads beside the address")
    .option("--label <name>")
    .action(async (flags) =>
      addCarrier({
        kind: "email",
        address: flags.address,
        imapHost: flags.imapHost,
        smtpHost: flags.smtpHost,
        imapPort: flags.imapPort,
        smtpPort: flags.smtpPort,
        username: flags.username,
        smtpUsername: flags.smtpUsername,
        senderName: flags.name,
        label: flags.label,
      }),
    );
  carriers
    .command("drop")
    .description("an account let go; its numbers stay routed until dropped")
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
    .description("which phone is yours: its calls reach your own agent, at the test line or at a production number")
    .argument("<number>", "+E.164")
    .option("--agent <name>", "the agent a call from it reaches; left out, the one the org holds")
    .action(async (number, flags) => ctx.io.result(await service.setCallerNumber(ctx, number, flags.agent), render.calling));
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
    .command("dial")
    .description("have an agent call a number, with what its call opens with")
    .argument("<agent>", "the agent's slug")
    .argument("<number>", "the number to call, in +E.164")
    .option("--from <number>", "which of the agent's numbers the far end sees")
    .option("--state <json>", "the state the agent's call opens in")
    .option("--metadata <json>", "what the call's call.started carries")
    .option("--greeting <words>", "the words this call opens with, over the agent's own greeting")
    .option("--instruction <words>", "what this call is for: the agent reads it for the whole call")
    .addHelpText("after", DIAL)
    .action(async (agent, number, flags) => {
      const input = service.DialInput.parse({ agent, to: number, from: flags.from, state: jsonOf("--state", flags.state), metadata: jsonOf("--metadata", flags.metadata), greeting: flags.greeting, instruction: flags.instruction });
      ctx.io.result(await service.dialOut(ctx, input), render.dialed);
    });

  program
    .command("text")
    .description("have an agent send a contact one SMS, or the first email of a thread")
    .argument("<agent>", "the agent's slug")
    .argument("<to>", "the contact's number, in +E.164, or their email address")
    .argument("[words]", "what the contact reads; an email's may be left to the agent")
    .option("--from <number>", "which of the agent's SMS numbers, or email addresses, it leaves from")
    .option("--subject <words>", "an email's subject: the thread's, and every reply's after it")
    .option("--metadata <json>", "what the conversation's call.started carries")
    .option("--instruction <words>", "what this conversation is for: the agent reads it throughout")
    .addHelpText("after", TEXT)
    .action(async (agent, to, words, flags) => {
      const input = service.TextInput.parse({ agent, to, text: words, from: flags.from, subject: flags.subject, metadata: jsonOf("--metadata", flags.metadata), instruction: flags.instruction });
      ctx.io.result(await service.textOut(ctx, input), render.texted);
    });

  program
    .command("template")
    .description("have an agent send a contact one WhatsApp template; the sandbox answers and sends nothing")
    .argument("<agent>", "the agent's slug")
    .argument("<name>", "the template's name, as Meta approved it")
    .requiredOption("--to <number>", "the contact's number, in +E.164")
    .requiredOption("--language <code>", "Meta's code of the language it was approved in: es_AR, en_US")
    .option("--var <words>", "what fills the body's next {{n}}; again for another, in order", repeated)
    .option("--from <number>", "which of the agent's WhatsApp numbers it leaves from")
    .option("--text <words>", "what the template says once filled: the first turn of the contact's conversation")
    .option("--metadata <json>", "what that conversation's call.started carries")
    .addHelpText("after", TEMPLATE)
    .action(async (agent, name, flags) => {
      const input = service.TemplateInput.parse({ agent, to: flags.to, template: name, language: flags.language, variables: flags.var, from: flags.from, text: flags.text, metadata: jsonOf("--metadata", flags.metadata) });
      ctx.io.result(await service.templateOut(ctx, input), render.templated);
    });

  program
    .command("callbacks")
    .description("the numbers people left when every seat was taken: who to call back")
    .option("--agent <slug>")
    .option("--after <cursor>")
    .addHelpText("after", CALLBACKS)
    .action(async (flags) => {
      const after = flags.after === undefined ? undefined : Number(flags.after);
      if (after !== undefined && !Number.isInteger(after)) throw new UsageError(`--after takes the cursor the page before answered, not ${flags.after}`);
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
