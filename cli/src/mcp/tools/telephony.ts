/** The `line`, `numbers`, `carriers`, `dial`, `text`, `email`, `callbacks` and `compliance` tools: the telephony domain and who may be reached, over their services. */

import { z } from "zod";

import * as dataRender from "../../calls/render.js";
import * as emailService from "../../email/service.js";
import * as data from "../../calls/service/data.js";
import * as service from "../../telephony/service.js";
import { tool, ToolRefused } from "../tool.js";
import { AGENT } from "./fields.js";

export const line = tool({
  name: "line",
  title: "Phone line",
  destroys: true,
  machine: true,
  description: "Who answers the agent's number right now and who could take it; which phone is the person's own, so their calls reach their copy.",
  schema: {
    action: z.enum(["show", "from", "forget", "claim", "release"]).describe("show whose process a ring lands in; from says which phone is the person's own; forget drops it; claim takes the line for this copy; release gives it back"),
    agent: AGENT.describe("the agent's name; the project's only agent when left out. `from`: the agent a call from the phone reaches"),
    number: z.string().optional().describe("`from`: the person's own phone, in +E.164"),
  },
  manual:
    "`line show` says whose process a ring at the agent's number lands in. `from <number>` says which phone is the person's own, once: a call from it reaches their sandbox agent (`agent` names which; left out, the one the org holds) at the box's test line, which the answer names, or at a production number, where everybody else reaches production. `claim` takes the line for this copy, `release` gives it back, `forget` drops the phone.",
  handler: async (args, ctx) => {
    if (args.action === "from") {
      if (args.number === undefined) throw new ToolRefused("from takes the person's own phone, in +E.164");
      return await service.setCallerNumber(ctx, args.number, args.agent);
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
  title: "Phone numbers",
  destroys: true,
  description: "The org's numbers and the agent each reaches; the numbers its carrier accounts own; importing one, or buying one on the deployment's account, shown as steps before anything is written.",
  schema: {
    action: z.enum(["list", "available", "import", "buy"]).describe("list the org's numbers; available is what its carrier accounts own; import points one of them at an agent; buy gets a new one on the deployment's account — import and buy are a dry run unless dry_run is false"),
    number: z.string().optional().describe("`import`: the number, in +E.164; for `email`, the mailbox's address"),
    agent: z.string().optional().describe("`import`, `buy`: the agent that answers it"),
    channel: z.enum(["phone", "whatsapp", "sms", "email"]).optional().describe("`import`, `buy`: phone unless said. One number answers on several: import it once a channel. `sms` is a number of a Twilio account, whose messages Twilio then posts to Pinecall; `email` is a mailbox account's address, whose inbox Pinecall reads"),
    account: z.string().optional().describe("`available`, `import`: the carrier account the number lives in, when the org has several (`carriers list` names them)"),
    move: z.boolean().optional().describe("`import`: take the number off the trunk it is on now (another environment's, or another agent's), as a 409 naming that trunk asks"),
    country: z.string().optional().describe("`buy`: the country, two letters (ES, US)"),
    area_code: z.string().optional().describe("`buy`: an area code, digits only"),
    dry_run: z.boolean().optional().describe("`import`, `buy`: true (the default) answers the steps and writes nothing; false does them"),
  },
  manual:
    "`numbers list` shows which number reaches which agent in the sandbox; `available` what the org's carrier accounts own. `import` points a number an account owns at an agent; when the org has several accounts, name the one that owns it in `account`, or ask the person which. `buy` gets a new number in `country` (and `area_code`) on the deployment's own account and points it at the agent; a bought number counts against the org's `numbers` limit (`usage` shows it), an imported one never does. One number answers on several channels, each its own route: `channel: \"whatsapp\"` for the number a WhatsApp account is, `channel: \"sms\"` for a Twilio number's text messages (Twilio is then told to post them to Pinecall; a number whose messages go to another service is refused until `move: true`). What the number answers on the other channels stays. Both first answer the steps they would take and write nothing; call again with `dry_run: false` to do them, after the person agreed. Letting a number go is never a tool: `pinecall numbers drop` in a terminal.",
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
  title: "Carrier accounts",
  reads: true,
  description: "The org's carrier accounts — Twilio, a SIP peer, WhatsApp, a mailbox — and one account's networks and how outbound calls leave. Never a secret.",
  schema: { action: z.enum(["list", "show"]).describe("list the org's carrier accounts, or show one"), account: z.string().optional().describe("`show`: the account's id") },
  manual: "`carriers` lists the org's carrier accounts and shows one. Adding one takes its secret, and the rule is that no key is printed or passed through an assistant, so it is never a tool: give the person the command to type in their own terminal, `pinecall carriers add twilio --account-sid AC… --user SK…` (`sip`, `whatsapp` and `email --address … --imap-host … --smtp-host …` the same way), which reads the secret with nothing echoed.",
  handler: async (args, ctx) => {
    if (args.action === "show") return await service.showCarrier(ctx, args.account);
    return { carriers: await service.listCarriers(ctx) };
  },
});

export const dial = tool({
  name: "dial",
  title: "Place a call",
  destroys: true,
  description: "Have an agent call a phone number, with the state its call opens in. The org's dial guards decide: who may be called, when, and how often.",
  schema: {
    agent: z.string().min(1).describe("the agent that places the call: its slug"),
    to: z.string().min(1).describe("the number to call, in +E.164"),
    from: z.string().optional().describe("which of the agent's own numbers the far end sees; the first when left out"),
    state: z.record(z.string(), z.unknown()).optional().describe("the state the agent's call opens in"),
    metadata: z.record(z.string(), z.unknown()).optional().describe("what the call's `call.started` carries"),
    greeting: z.string().optional().describe("the words this call opens with, over the agent's own greeting"),
    instruction: z.string().optional().describe("what this call is for: the agent reads it for the whole call and, with no greeting, opens on it"),
  },
  manual:
    "`dial` places a call as the agent and answers before anything rings: the call's id, the number shown and the environment. Somebody must be holding the agent, or the dial is refused. A dial the org's guards refuse (a stranger, quiet hours, no consent, too many) says which guard refused it. `call` reads the call's log afterwards.",
  handler: async (args, ctx) => await service.dialOut(ctx, service.DialInput.parse(args)),
});

export const text = tool({
  name: "text",
  title: "Send an SMS",
  destroys: true,
  description: "Have an agent send a contact one SMS first, from a number it answers SMS at. The org's dial guards decide: who may be reached, when, and how often.",
  schema: {
    agent: z.string().min(1).describe("the agent that writes: its slug"),
    to: z.string().min(1).describe("the contact's number, in +E.164"),
    text: z.string().min(1).max(1600).describe("what the contact reads"),
    from: z.string().optional().describe("which of the agent's SMS numbers it leaves from; the first when left out"),
  },
  manual:
    "`text` sends a contact one SMS as the agent and answers with the conversation it was said on: the call's id, the number it left from and the environment. What the contact answers reaches the agent on that conversation, with these words before it. Somebody must be holding the agent, and the agent must answer SMS at a number (`numbers` imports one with `channel: sms`). A contact whose conversation is still open is written on it; any other passes the org's guards as a dial does (a stranger, no consent, quiet hours, too many today), and a refusal says which guard and sends nothing. A contact who texted STOP is refused whatever else is true: `compliance consent` says who did.",
  handler: async (args, ctx) => await service.textOut(ctx, service.TextInput.parse(args)),
});

export const email = tool({
  name: "email",
  title: "Email layout",
  destroys: true,
  description: "How the org's agents' emails are set: an HTML layout shown, kept, tried on words (nothing sent) or cleared back to the plain one, or text alone with no template.",
  schema: {
    action: z.enum(["show", "set", "text", "preview", "clear"]).describe("show how the emails are set; set keeps html as the org's layout; text sends them as text alone, no template and no HTML; preview sets words as a reply would be, sending nothing; clear goes back to the plain layout"),
    html: z.string().optional().describe("`set`, `preview`: an HTML page that says {{content}} once, where the reply goes, and {{subject}} where the subject should show"),
    text: z.string().optional().describe("`preview`: the words an agent would write: paragraphs, - lists, **bold**, *italics*, links"),
    subject: z.string().optional().describe("`preview`: the subject the reply answers"),
    text_only: z.boolean().optional().describe("`preview`: the email as text alone, with no HTML, whatever the org keeps"),
  },
  manual:
    "`email` keeps the org's email layout: an agent answers an email in its own words and they are set in it, `{{content}}` where the reply goes, `{{subject}}` where the subject shows; with none, a plain one. `text` is for an org that wants no template: its emails go as their words alone, one text part and no HTML, until a layout is `set` or it is `clear`ed. `preview` answers the subject, the HTML and the plain part a contact would read, and sends nothing: try a layout on it before `set`. A mailbox is a carrier account (`carriers`), and its address is given to an agent with `numbers import` on the channel `email`.",
  handler: async (args, ctx) => {
    if (args.action === "show") return await emailService.showLayout(ctx);
    if (args.action === "clear") return await emailService.clearLayout(ctx);
    if (args.action === "text") return await emailService.sendTextOnly(ctx);
    if (args.action === "set") {
      if (args.html === undefined) throw new ToolRefused("set takes the html, saying {{content}} once");
      return await emailService.keepLayout(ctx, args.html);
    }
    if (args.text === undefined) throw new ToolRefused("preview takes the text an agent would write");
    return await emailService.previewWords(ctx, { text: args.text, ...(args.subject === undefined ? {} : { subject: args.subject }), ...(args.html === undefined ? {} : { html: args.html }), ...(args.text_only === undefined ? {} : { text_only: args.text_only }) });
  },
});

export const callbacks = tool({
  name: "callbacks",
  title: "Callbacks",
  reads: true,
  description: "The callers waiting to be called back, oldest first: who, on which channel, through what (the overflow, the agent's own tool, the widget).",
  schema: { agent: z.string().optional().describe("only this agent's"), after: z.number().int().min(0).optional().describe("where the page before ended") },
  manual: "`callbacks` lists the people waiting for a call back, each with the call it came from.",
  handler: async (args, ctx) => await service.listCallbacks(ctx, service.ListCallbacksInput.parse(args)),
});

export const compliance = tool({
  name: "compliance",
  title: "Consent and opt-outs",
  destroys: true,
  description: "The org's rules for who may be called and written to: the policy, what a contact who texts STOP or HELP is told, what stands for one number, and the do-not-call list.",
  schema: {
    action: z.enum(["policy", "sms", "consent", "dnc"]).describe("policy reads the org's rules; sms sets what a contact who texts STOP or HELP is told; consent says what stands for one number; dnc lists the numbers nobody calls or writes to"),
    number: z.string().optional().describe("`consent`: the number, in +E.164"),
    stop_reply: z.string().max(320).optional().describe("`sms`: the one sentence a contact is told when they are taken off; an empty string tells them nothing"),
    carrier_stop_reply: z.boolean().optional().describe("`sms`: true goes back to the default — the carrier confirms a stop word, and the platform's sentence follows an opt-out the agent took"),
    help_reply: z.string().max(320).optional().describe("`sms`: what a contact who texts HELP is told; an empty string leaves the word to the carrier and the agent"),
    stop_words: z.array(z.string()).optional().describe("`sms`: more words that stop the messages, beside the standard ones; an empty list keeps the standard ones alone"),
    after: z.string().optional().describe("`dnc`: where the page before ended"),
  },
  manual:
    "`compliance policy` reads the org's rules: how long a call is kept, when and how often a number is rung, who needs a consent on file, what an outbound call opens with, and what a contact who texts STOP or HELP is told. `sms` changes that last part alone, one field at a time: `stop_reply`, `help_reply`, `stop_words` (the words of the contacts' own language, beside STOP, UNSUBSCRIBE, CANCEL, END, QUIT). A contact who texts a stop word is taken off before the model reads anything and is written to no more until they text START; that is not a setting. `consent` says what stands for one number (consented, on the list, nothing on file) with every fact about it, newest first: who stopped, when, and in which words. `dnc` lists the numbers on the list. The rest of the policy, a consent given and a number put on the list by hand stay `pinecall data` verbs a person types.",
  handler: async (args, ctx) => {
    if (args.action === "consent") {
      if (args.number === undefined) throw new ToolRefused("consent names the number, in +E.164");
      const history = await data.consent(ctx, data.ConsentInput.parse({ number: args.number }));
      return { ...history, says: dataRender.consent(history) };
    }
    if (args.action === "dnc") return await data.listDoNotCall(ctx, args.after);
    const changes =
      args.action === "sms"
        ? {
            ...(args.stop_reply === undefined ? {} : args.stop_reply.trim() === "" ? { noSmsStopReply: true } : { smsStopReply: args.stop_reply }),
            ...(args.carrier_stop_reply === true ? { carrierStopReply: true } : {}),
            ...(args.help_reply === undefined ? {} : args.help_reply.trim() === "" ? { carrierHelpReply: true } : { smsHelpReply: args.help_reply }),
            ...(args.stop_words === undefined ? {} : args.stop_words.length === 0 ? { standardStopWords: true } : { smsStopWords: args.stop_words.join(",") }),
          }
        : {};
    if (args.action === "sms" && Object.keys(changes).length === 0) throw new ToolRefused("sms takes stop_reply, carrier_stop_reply, help_reply or stop_words");
    const row = await data.policy(ctx, data.PolicyInput.parse(changes));
    return { ...row, says: dataRender.policy(row) };
  },
});
