/** `pinecall sessions | chat | supervise | data`: an agent's calls, a written call, a live call's desk, the org's data. */

import { createInterface, type Interface } from "node:readline";

import type { Command } from "@commander-js/extra-typings";

import { connectionLine, type Context } from "../context.js";
import { errorMessage, UsageError } from "../errors.js";
import { listOf, numberOf } from "../kit/flags.js";
import * as render from "./render.js";
import * as service from "./service/index.js";

const SESSIONS = `
With nothing after it: every call this agent has run, newest first — when it came in, how long
it lasted, why it ended, what it cost and the one line the agent left as its outcome. With a
call id: that call whole — the same facts, and the SCORE, one line per judge that ran over it.
log <call>: the call's log as the runtime keeps it, an entry a line, ${service.A_PAGE} entries a page.
--agent names the agent from any folder; beside an agent's class it is that agent.

Examples
  $ pinecall sessions --limit 3
  $ pinecall sessions call_5b1f0e9d2c7a4e8f9a1b3c5d7e9f1a2b
  $ pinecall sessions log call_5b1f… --types turn.agent,tool.call
`;

const CHAT = `
A written call at the agent whoever holds it — your own \`pinecall start\` in another terminal,
a colleague's, production's with --prod. Nothing is started here. With nothing after it, the
agent of this directory; with a slug, that agent.

Examples
  $ pinecall chat --as +34600000001
  ‹ hi, I'd like to change my Thursday appointment
  › Of course. Could I have your full name and phone number?
`;

const SUPERVISE = `
The call's transcript as it happens, and one line to move on it:

${service.MOVES.map(([key, what]) => `  ${key.padEnd(11)} ${what}`).join("\n")}

Every move lands in the caller's own log as its own \`supervisor.*\` entry with a seq. The audio of
a live call is the console, which has a room — \`pinecall start\` prints its URL.
`;

const DATA = `
What the org keeps in the env this key acts in (--prod for production), and taking it out.

erase call <id> is one ended call gone: its log, its facts, the memories it taught and its
recording. erase contact <who> is a person's "delete my data". erasures is the trail. reads is
who read the org's calls. policy is the org's compliance settings, one row; a flag changes one
field. consent is what stands for a number. dnc is the do-not-call list. export is the org's
env whole as JSON Lines. An erasure cannot be undone, so it asks for --yes.
`;

const ON_THE_SPEAKERS = "the audio of a live call is the console, which has a room — `pinecall start` prints its URL; this is the transcript and the desk";

export function register(program: Command, ctx: Context): void {
  const sessions = program
    .command("sessions")
    .description("an agent's calls; one call whole, with what it cost and how it was judged; or its log")
    .argument("[call]", "a call id: that call whole; every call of the agent when left out")
    .option("--agent <slug>", "the agent, from any folder; the one beside you when left out")
    .option("--limit <n>", "how many calls, newest first")
    .addHelpText("after", SESSIONS)
    .action(async (call, flags) => {
      if (call !== undefined) return ctx.io.result(await service.showCall(ctx, call), render.call);
      ctx.io.result(await service.listSessions(ctx, service.ListSessionsInput.parse({ agent: flags.agent, limit: numberOf("--limit", flags.limit) })), render.sessions);
    });
  sessions
    .command("log")
    .description("the call's log as the runtime keeps it, an entry a line")
    .argument("<call>")
    .option("--after <seq>", "read on from there")
    .option("--limit <n>", `entries a page, at most 500; ${service.A_PAGE} when left out`)
    .option("--types <a.b,c.d>", "only these entry types")
    .action(async (call, flags) => {
      // `sessions` has a --limit of its own, and commander hands a flag both have to the group: read it there too.
      const limit = flags.limit ?? sessions.opts().limit;
      const input = service.ReadLogInput.parse({ call, after: numberOf("--after", flags.after), limit: numberOf("--limit", limit), types: listOf(flags.types) });
      ctx.io.result(await service.readLog(ctx, input), (page) => render.log(page, input.after));
    });

  program
    .command("chat")
    .description("a written caller against the agent, wherever it is held")
    .argument("[agent]", "the agent's slug; the agent of this directory when left out")
    .option("--agent <name>")
    .option("--file <agent.tsx>")
    .option("--as <contact>", "who is calling: the id memory files this call under")
    .option("--state <file>", "the state the call opens in: a goldens file")
    .option("--case <n>", "which case of that file")
    .option("--events", "one JSON line per log entry instead of the lines, for a pipe")
    .addHelpText("after", CHAT)
    .action(async (slug, flags) => {
      const agent = slug ?? ctx.agent("chat", { file: flags.file, agent: flags.agent }).name;
      const state = flags.state === undefined ? undefined : service.stateOfCase(flags.state, numberOf("--case", flags.case));
      await chatAtTheTerminal(ctx, { agent, contact: flags.as, state }, flags.events === true);
    });

  program
    .command("supervise")
    .description("listen in: whisper, say, take the line, give it back, end")
    .argument("<call>")
    .addHelpText("after", SUPERVISE)
    .action(async (call) => {
      await service.liveCall(ctx, call);
      ctx.io.print(`${call} · ${ON_THE_SPEAKERS}`);
      await atTheDesk(ctx, call);
    });

  const data = program.command("data").description("the org's data: erasures, the policy, consent, the do-not-call list, export").addHelpText("after", DATA);
  const erase = data.command("erase").description("one ended call, or everything about a contact, gone");
  erase
    .command("call")
    .description("one ended call: its log, facts, memories and recording")
    .argument("<call-id>")
    .option("--yes", "an erasure cannot be undone")
    .action(async (call, flags) => {
      if (flags.yes !== true) throw new UsageError(service.SAY_YES("call", call));
      ctx.io.result(await service.eraseCall(ctx, call), render.erased);
    });
  erase
    .command("contact")
    .description("everything about one contact: their calls and every fact kept of them")
    .argument("<number|id>")
    .option("--yes")
    .action(async (who, flags) => {
      if (flags.yes !== true) throw new UsageError(service.SAY_YES("contact", who));
      ctx.io.result(await service.eraseContact(ctx, who), render.erased);
    });
  data.command("erasures").description("the trail: what was erased, when, and who asked").action(async () => ctx.io.result(await service.listErasures(ctx), render.erasures));
  data
    .command("reads")
    .description("who read the org's calls")
    .argument("[call-id|number]")
    .action(async (subject) => ctx.io.result(await service.listReads(ctx, subject), render.reads));
  const policy = data
    .command("policy")
    .description("the org's compliance settings, one row; a flag changes one field")
    .option("--retention-days <n>")
    .option("--keep-all")
    .option("--calling-hours <from-until>")
    .option("--any-hours")
    .option("--per-number-day <n>")
    .option("--no-per-number")
    .option("--consent-everywhere")
    .option("--consent-by-law")
    .option("--disclosure <words>")
    .option("--platform-disclosure")
    .option("--no-disclosure")
    .option("--recording-notice")
    .option("--no-recording-notice");
  // commander keeps one value for `--x` and `--no-x`, the last said; both said is two answers to one
  // field, which the service refuses. Each flag is heard as it is read, so both are known.
  const said = new Map<string, unknown>();
  for (const name of ["disclosure", "no-disclosure", "recording-notice", "no-recording-notice"]) policy.on(`option:${name}`, (value: unknown) => said.set(name, value));
  policy.action(async (flags) => {
      const input = service.PolicyInput.parse({
        retentionDays: numberOf("--retention-days", flags.retentionDays),
        keepAll: flags.keepAll === true,
        callingHours: flags.callingHours,
        anyHours: flags.anyHours === true,
        perNumberDay: numberOf("--per-number-day", flags.perNumberDay),
        noPerNumber: flags.perNumber === false,
        consentEverywhere: flags.consentEverywhere === true,
        consentByLaw: flags.consentByLaw === true,
        disclosure: typeof said.get("disclosure") === "string" ? (said.get("disclosure") as string) : undefined,
        platformDisclosure: flags.platformDisclosure === true,
        noDisclosure: said.has("no-disclosure"),
        recordingNotice: said.has("recording-notice"),
        noRecordingNotice: said.has("no-recording-notice"),
      });
      ctx.io.result(await service.policy(ctx, input), render.policy);
    });
  data
    .command("consent")
    .description("what stands for a number, or a consent given or an opt-out recorded")
    .argument("<number>")
    .option("--give <kind>", "express | written")
    .option("--source <where>")
    .option("--text <agreed>")
    .option("--evidence <what>")
    .option("--opt-out", "put the number on the do-not-call list")
    .action(async (number, flags) => ctx.io.result(await service.consent(ctx, service.ConsentInput.parse({ number, give: flags.give, source: flags.source, text: flags.text, evidence: flags.evidence, optOut: flags.optOut === true })), render.consent));
  const dnc = data.command("dnc").description("the do-not-call list");
  dnc
    .command("list", { isDefault: true })
    .description("the numbers never to call, newest first, a page")
    .option("--after <cursor>")
    .action(async (flags) => ctx.io.result(await service.listDoNotCall(ctx, flags.after), render.doNotCall));
  dnc
    .command("add")
    .description("numbers put on the list, with where the request came from")
    .argument("<numbers...>")
    .requiredOption("--source <where>")
    .action(async (numbers, flags) => ctx.io.result(await service.addDoNotCall(ctx, numbers, flags.source), render.doNotCallAdded));
  dnc
    .command("import")
    .description("a file of numbers, one a line, put on the list")
    .argument("<file>", "one number a line")
    .requiredOption("--source <where>")
    .action(async (file, flags) => ctx.io.result(await service.importDoNotCall(ctx, file, flags.source), render.doNotCallAdded));
  data
    .command("export")
    .description("the org's env whole as JSON Lines")
    .option("--out <file.jsonl>", "write a file; stdout when left out")
    .action(async (flags) => {
      const done = await service.exportOrg(ctx, flags.out ?? ctx.io.stdout);
      if (done.file !== null) ctx.io.info(`${connectionLine(ctx)}\nthe org's ${ctx.env} env written to ${done.file}`);
    });
}

// Each typed line is one turn; each frame is one log entry, printed as it lands. Input that ends
// (a pipe) leaves only once every line sent was heard and answered.
async function chatAtTheTerminal(ctx: Context, options: service.ChatOptions, events: boolean): Promise<void> {
  // stdin is read only once the call is open: a pipe's lines arrive at once, and one read before
  // the socket is up would be said to nobody and the pipe's end would hang up a call never spoken to.
  let lines: Interface | undefined;
  const prompt = (): void => {
    if (ctx.io.interactive) lines?.prompt();
  };
  let closed = false;
  const chat = await service.Chat.open(ctx, options, {
    onEntry: (entry, raw) => {
      const line = events ? raw : render.chatLine(entry);
      if (line === null) return;
      // Redraw the prompt: an entry may land mid-typing.
      ctx.io.stdout.write(`\r${line}\n`);
      if (!closed) prompt();
    },
    onLost: () => ctx.io.info("\rthe gateway went away — the call is kept, reconnecting…"),
    onBack: () => ctx.io.info("\rthe gateway is back: the call goes on"),
  });
  lines = createInterface({ input: process.stdin, output: ctx.io.stdout, prompt: `${render.CALLER} ` });
  prompt();
  // A pipe's lines all arrive at once: each is said once the one before was answered, as a person
  // types, or a line reached the model while a tool of the one before still ran (T F4, R F4).
  let turns = Promise.resolve();
  lines.on("line", (line) => {
    const said = line.trim();
    if (said !== "" && ctx.io.interactive) chat.say(said);
    else if (said !== "") turns = turns.then(() => chat.sayAndWait(said)).catch(() => undefined);
    prompt();
  });
  lines.on("close", () => {
    closed = true;
    void turns.then(() => chat.untilAnswered()).then(() => chat.end());
  });
  const why = await chat.done();
  lines.close();
  if (why !== "") throw new UsageError(why);
}

/** Tail the log and read moves concurrently; neither waits for the other. */
async function atTheDesk(ctx: Context, call: string): Promise<void> {
  const input = process.stdin;
  const lines = createInterface({ input, output: ctx.io.stdout, prompt: "> " });
  const leaving = new AbortController();
  let ended = false;
  let left = false;
  const watching = (async () => {
    for await (const entry of service.followCall(ctx, call, 0, leaving.signal)) {
      const line = render.deskLine(entry);
      if (line !== null) ctx.io.stdout.write(`\r${line}\n`);
      prompting(lines, ctx, left);
      if (entry.type === "call.ended") ended = true;
      if (ended) break;
    }
  })();
  prompting(lines, ctx, left);
  for await (const typed of lines) {
    if (ended) break;
    const move = service.moveOf(typed.trim());
    if (move === "leave") break;
    if (move === null) ctx.io.info(`\rnot a move. ${service.MOVES.map(([key]) => key.split(" ")[0]).join(" · ")}`);
    else await service.sendMove(ctx, call, move).then(() => ctx.io.info(`\r${move.verb} sent`), (refused: unknown) => ctx.io.info(`\r${errorMessage(refused)}`));
    prompting(lines, ctx, left);
  }
  // Abort the tail rather than awaiting it: it may be waiting on an entry that never comes.
  left = true;
  leaving.abort();
  lines.close();
  await watching.catch(() => undefined);
}

// Draw the prompt only on a TTY, and never after the interface is closed: the tail can outlive it.
function prompting(lines: Interface, ctx: Context, left: boolean): void {
  if (!left && ctx.io.interactive) lines.prompt();
}
