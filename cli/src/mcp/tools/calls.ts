/** The `calls`, `call`, `chat` and `supervise` tools: the calls domain, over its service. */

import { z } from "zod";

import * as service from "../../calls/service/index.js";
import { ToolRefused, tool } from "../tool.js";
import { AGENT, needed, WAIT, WAIT_S } from "./fields.js";

export const ENDED = (call: string): string => `${call} has ended, and a desk moves a call that is happening: \`call\` reads what it was`;

export const calls = tool({
  name: "calls",
  description: "The agent's newest calls: each one's id, channel, length, how it ended, its cost and its verdicts.",
  schema: { agent: AGENT, limit: z.number().int().min(1).max(100).optional().describe("how many, newest first; 20 when left out") },
  manual: "`calls` lists the agent's newest calls with their ids; `call` reads one whole.",
  handler: async (args, ctx) => await service.listSessions(ctx, { agent: args.agent, limit: args.limit ?? 20 }),
});

export const call = tool({
  name: "call",
  description: "One call's log, entry by entry — every turn, tool call, result, state change, metric and verdict — a page at a time.",
  schema: {
    call: z.string().describe("the call's id"),
    after: z.number().int().min(0).optional().describe("only entries after this seq: the `next` of the page before"),
    limit: z.number().int().min(1).max(500).optional().describe("entries in this page; 200 when left out"),
    types: z.array(z.string()).optional().describe("only these entry types, such as turn.agent or call.score"),
  },
  manual:
    "`call` reads one call's log the way the runtime keeps it: every entry with its seq, quiet ones included — the turns, each tool call and its result, the state after it, the latency of each turn, the cost, and the verdicts at hang-up (`call.score`). Page with `after` set to the `next` the page before answered, until `next` is null; `types` narrows a page and never ends the reading early. `live` says the call is still going.",
  handler: async (args, ctx) => await service.readLog(ctx, service.ReadLogInput.parse(args)),
});

/** One entry of the call as a model reads it. */
type Heard = { agent: string } | { tool: string; args: unknown } | { result: string; output: unknown } | { state: Record<string, unknown> } | { error: string };

export const chat = tool({
  name: "chat",
  description: "Talk to the agent as a caller, wherever it is held: `say` a line (opening a call, or continuing one by its id) and get its whole answer; `end` hangs up.",
  schema: {
    action: z.enum(["say", "end"]).describe("say a line as the caller, opening a call or continuing `call`; end hangs `call` up"),
    text: z.string().optional().describe("`say`: what the caller says"),
    call: z.string().optional().describe("the call to continue or end; a new call opens when left out"),
    agent: AGENT,
    contact: z.string().optional().describe("who is calling (a phone number), so memory files the call under them"),
    state: z.record(z.string(), z.unknown()).optional().describe("the state a new call opens in"),
  },
  manual:
    "`chat` is a written call with the agent: the copy `start` holds when it holds it in the env asked, else whoever holds it there — a terminal, a colleague, production's own process — with nothing started. `say` without `call` opens one and answers with its id; pass that id to go on. Each answer is everything the agent did for that line: its turns, the tools it called with their arguments, their results, the state it changed. `end` hangs up, and the call is judged like any other. `contact` makes the caller someone, so memory is written and recalled.",
  handler: async (args, ctx) => {
    const talks = ctx.session.talks;
    if (args.action === "end") {
      const id = needed(args.call, "call");
      const talk = talks.get(id);
      if (talk === undefined) throw new ToolRefused(`no open call ${id} here: say a line without \`call\` to open one`);
      talks.delete(id);
      await talk.chat.end();
      return { call: id, heard: [], ended: true };
    }
    const text = needed(args.text, "text");
    if (args.call !== undefined) {
      const talk = talks.get(args.call);
      if (talk === undefined) throw new ToolRefused(`no open call ${args.call} here: say a line without \`call\` to open one`);
      if (talk.chat.ended) talks.delete(args.call);
      return await said(talk, text);
    }
    const reached = await ctx.session.reach(ctx, args.agent);
    const heard: Heard[] = [];
    const talk = { chat: await service.Chat.open(ctx, { agent: reached.slug, app: reached.app, contact: args.contact, state: args.state }, { onEntry: (entry) => void take(heard, entry) }), heard };
    const answer = await said(talk, text);
    if (answer.call !== null && !answer.ended) talks.set(answer.call, talk);
    return { ...answer, env: ctx.env, ...(reached.version === undefined ? {} : { version: reached.version }) };
  },
});

/** A written call the server keeps open between tool calls: the chat, and what was heard since the last line. */
export interface Talk {
  chat: service.Chat;
  heard: Heard[];
}

async function said(talk: Talk, text: string): Promise<{ call: string | null; heard: Heard[]; ended: boolean }> {
  talk.heard.length = 0;
  await talk.chat.sayAndWait(text);
  if (!talk.chat.ended && !talk.chat.settled) talk.heard.push({ error: `no answer within ${service.ANSWERS_WITHIN_MS / 1000}s` });
  return { call: talk.chat.call, heard: [...talk.heard], ended: talk.chat.ended };
}

function take(heard: Heard[], entry: service.Entry): void {
  const data = entry.data;
  switch (entry.type) {
    case "turn.agent":
      return void heard.push({ agent: String(data["text"] ?? "") });
    case "tool.call":
      return void heard.push({ tool: String(data["name"] ?? "?"), args: data["arguments"] ?? {} });
    case "tool.result":
      if (data["error"] !== undefined && data["error"] !== null) return void heard.push({ error: `${String(data["name"] ?? "tool")}: ${String(data["error"])}` });
      return void heard.push({ result: String(data["name"] ?? "?"), output: data["output"] ?? data["summary"] ?? null });
    case "state.changed":
      return void heard.push({ state: (data["state"] as Record<string, unknown> | undefined) ?? {} });
    case "error":
      return void heard.push({ error: String(data["message"] ?? "") });
    default:
      return;
  }
}

export const supervise = tool({
  name: "supervise",
  description: "A live call, as a supervisor's desk sees it: its transcript as it happens (`watch`), and a move on it — whisper to the agent, say a line in its voice, take the line, give it back, transfer, end.",
  schema: {
    action: z.enum(["watch", "whisper", "say", "takeover", "release", "transfer", "end"]).describe("watch reads what was said since `after`, waiting up to wait_s for more; whisper tells the agent something the caller never hears; say makes the agent say `text` verbatim; takeover silences the agent and puts a person on the line; release gives the line back; transfer sends the caller to `to`; end hangs up"),
    call: z.string().describe("the live call's id: `calls` lists the agent's newest, a live one marked live"),
    text: z.string().optional().describe("`whisper` and `say`: the words"),
    to: z.string().optional().describe("`transfer`: the number in +E.164, or the SIP address, the caller is sent to"),
    mode: z.enum(["cold", "warm"]).optional().describe("`transfer`: cold sends the caller at once; warm lets the agent introduce them first"),
    reason: z.string().optional().describe("`end`: why, kept in the call's log"),
    after: z.number().int().min(0).optional().describe("`watch`: the `next` the answer before ended at; the call's beginning when left out"),
    wait_s: WAIT,
  },
  manual:
    "`supervise` is the desk `pinecall supervise` is in a terminal, for a call that is happening. `watch` answers the call's lines since `after` — the caller's, the agent's, its tool calls, every move of a desk, the end — and waits up to `wait_s` for more while the call is live; pass the `next` it answers to keep reading. `whisper` reaches the agent as an instruction for its next reply and the caller never hears it; `say` puts words in the agent's voice; `takeover` silences the agent until `release`; `transfer` and `end` act on the caller, at once. Every move lands in the caller's own log as a `supervisor.*` entry. On a call that has ended `watch` answers what it was, `live: false`, and every move is refused: `call` reads it whole. The audio of a live call is the console's Live screen (`console_url`).",
  handler: async (args, ctx) => {
    if (args.action === "watch") return await service.watchCall(ctx, args.call, args.after ?? 0, args.wait_s ?? WAIT_S);
    const state = await service.callState(ctx, args.call);
    if (!state.live) throw new ToolRefused(ENDED(args.call));
    return await service.sendMove(ctx, args.call, verbOf(args));
  },
});

function verbOf(args: { action: string; text?: string | undefined; to?: string | undefined; mode?: "cold" | "warm" | undefined; reason?: string | undefined }): service.Verb {
  switch (args.action) {
    case "whisper":
    case "say":
      if (args.text === undefined || args.text.trim() === "") throw new ToolRefused(`${args.action} takes the words: text`);
      return { verb: args.action, text: args.text.trim() };
    case "transfer":
      if (args.to === undefined || args.to.trim() === "") throw new ToolRefused("transfer takes where the caller goes: to, a number in +E.164 or a SIP address");
      return { verb: "transfer", to: args.to.trim(), ...(args.mode === undefined ? {} : { mode: args.mode }) };
    case "end":
      return { verb: "end", ...(args.reason === undefined ? {} : { reason: args.reason }) };
    case "takeover":
      return { verb: "takeover" };
    default:
      return { verb: "release" };
  }
}
