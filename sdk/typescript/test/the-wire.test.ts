// Conformance: every command of the wire is sent by a part of this SDK or is not an SDK's to send,
// and every event is folded by one or ignored with a reason. A new wire entry fails here, by name.

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { COMMAND_SCHEMAS, EVENT_SCHEMAS } from "../src/wire/registry.js";

const SRC = new URL("../src/", import.meta.url);

/** The file that sends each command: the call's verbs, a room's seats, the call's frames, the socket's own. */
const COMMANDS: Record<string, string> = {
  "agent.say": "call/call.ts",
  "agent.reply": "call/call.ts",
  "room.send": "call/call.ts",
  "room.invite": "call/room.ts",
  "participant.mute": "call/room.ts",
  "participant.remove": "call/room.ts",
  "call.hangup": "call/call.ts",
  "call.transfer": "call/call.ts",
  "call.attention": "call/call.ts",
  "call.hold": "call/call.ts",
  "call.unhold": "call/call.ts",
  "call.dtmf": "call/call.ts",
  "call.claim": "call/call.ts",
  "call.callback": "call/call.ts",
  "call.opt_out": "call/call.ts",
  "call.log": "client/calls.ts",
  "call.event": "client/calls.ts",
  "prompt.set": "client/calls.ts",
  "tools.set": "client/calls.ts",
  "state.set": "client/calls.ts",
  "tool.result": "client/calls.ts",
  "agent.register": "client/agent.ts",
  "agent.configure": "client/agent.ts",
  "agent.drain": "client/agent.ts",
  "dev.answer": "client/agent.ts",
  "ping": "client/agent.ts",
};

/** Commands no SDK sends, and whose they are. */
const NOT_THE_SDKS: Record<string, string> = {
  "call.dial": "a call is placed through POST /v1/calls; the app socket refuses it",
  "call.mute": "the desk's: a supervisor mutes the agent",
  "call.unmute": "the desk's: a supervisor unmutes the agent",
  "session.configure": "the gateway's own, for a declaration it makes for one call",
  "supervisor.verb": "the desk's: a supervisor's socket, never an app's",
};

/** The file that folds each event this SDK acts on. */
const FOLDED: Record<string, string> = {
  "agent.registered": "client/agent.ts",
  "agent.configured": "client/agent.ts",
  "agent.draining": "client/agent.ts",
  "dev.request": "client/agent.ts",
  "tool.call": "client/agent.ts",
  "error": "client/agent.ts",
  "call.started": "runtime/connect.ts",
  "call.attached": "runtime/connect.ts",
  "event.received": "runtime/connect.ts",
  "memory.ops": "runtime/connect.ts",
  "call.ringing": "client/calls.ts",
  "call.dialing": "client/calls.ts",
  "state.changed": "client/calls.ts",
  "tool.result": "client/calls.ts",
  "turn.user": "call/call.ts",
  "turn.agent": "call/call.ts",
  "call.claimed": "call/call.ts",
  "call.transferred": "call/call.ts",
  "attention.answered": "call/call.ts",
  "participant.joined": "call/call.ts",
  "participant.left": "call/call.ts",
  "participant.speaking": "call/call.ts",
  "call.ended": "call/call.ts",
};

const A_MEASURE = "a measure for the console and the evals; an app reads it with call.on";
const THE_DESKS = "what a supervisor did, for the desk; an app reads it with call.on";
const THE_LOGS = "the log's own bookkeeping, for a reader of the log";
const THE_GATEWAYS = "the gateway's record of the call, read by the console and the judges";

/** Events this SDK leaves to `call.on` / `pc.onAny`, and why. */
const IGNORED: Record<string, string> = {
  "agent.detached": "the gateway's record that a socket let the agent go",
  "agent.state": THE_GATEWAYS,
  "agent.transcript": "a partial line, for a live screen",
  "app.failed": THE_GATEWAYS,
  "user.transcript": "a partial line, for a live screen",
  "user.state": THE_GATEWAYS,
  "attention.requested": THE_GATEWAYS,
  "call.line": THE_GATEWAYS,
  "call.score": THE_GATEWAYS,
  "call.summary": THE_GATEWAYS,
  "callback.requested": THE_GATEWAYS,
  "code.claimed": THE_GATEWAYS,
  "code.issued": THE_GATEWAYS,
  "confirm.request": THE_GATEWAYS,
  "confirm.granted": THE_GATEWAYS,
  "confirm.declined": THE_GATEWAYS,
  "credits.exhausted": THE_GATEWAYS,
  "evals.spent": THE_GATEWAYS,
  "custom": "an app's own entry, read back by whoever wrote it",
  "docs.sources": THE_GATEWAYS,
  "dtmf.received": "a tone the caller keyed; an app that reads a menu takes it with call.on",
  "fleet.full": THE_GATEWAYS,
  "release.changed": THE_GATEWAYS,
  "run.changed": THE_GATEWAYS,
  "tool.ran": THE_GATEWAYS,
  "tool.failed": THE_GATEWAYS,
  "judge.broke": THE_GATEWAYS,
  "worker.changed": THE_GATEWAYS,
  "message.taken": THE_GATEWAYS,
  "message.waiting": THE_GATEWAYS,
  "prompt.changed": THE_GATEWAYS,
  "tools.changed": THE_GATEWAYS,
  "room.opened": THE_GATEWAYS,
  "room.sent": THE_GATEWAYS,
  "track.published": THE_GATEWAYS,
  "track.unpublished": THE_GATEWAYS,
  "spend.unusual": THE_GATEWAYS,
  "vendor.switched": THE_GATEWAYS,
  "log.caught_up": THE_LOGS,
  "log.gap": THE_LOGS,
  "pong": "the answer to ping, which keeps the socket warm",
  "metrics.avatar": A_MEASURE,
  "metrics.eot": A_MEASURE,
  "metrics.eou": A_MEASURE,
  "metrics.interruption": A_MEASURE,
  "metrics.llm": A_MEASURE,
  "metrics.realtime": A_MEASURE,
  "metrics.stt": A_MEASURE,
  "metrics.tts": A_MEASURE,
  "metrics.vad": A_MEASURE,
  "supervisor.ended": THE_DESKS,
  "supervisor.released": THE_DESKS,
  "supervisor.said": THE_DESKS,
  "supervisor.took_over": THE_DESKS,
  "supervisor.transferred": THE_DESKS,
  "supervisor.whispered": THE_DESKS,
};

const sourceOf = (file: string): string => readFileSync(new URL(file, SRC), "utf8");

/** Every name of the registry in no table, and every row naming nothing the registry has. */
function strays(registry: string[], tables: Record<string, string>[]): { unowned: string[]; unknown: string[]; twice: string[] } {
  const rows = tables.flatMap((table) => Object.keys(table));
  return {
    unowned: registry.filter((name) => !rows.includes(name)),
    unknown: rows.filter((name) => !registry.includes(name)),
    twice: rows.filter((name, at) => rows.indexOf(name) !== at),
  };
}

describe("the commands of the wire", () => {
  it("are each sent by one part of this SDK or said to be nobody's here", () => {
    expect(strays(Object.keys(COMMAND_SCHEMAS), [COMMANDS, NOT_THE_SDKS])).toEqual({ unowned: [], unknown: [], twice: [] });
  });

  it("are each written by name in the file the table says sends it", () => {
    const missing = Object.entries(COMMANDS).filter(([command, file]) => !sourceOf(file).includes(`"${command}"`));
    expect(missing).toEqual([]);
  });
});

describe("the events of the wire", () => {
  it("are each folded by one part of this SDK or ignored with a reason", () => {
    expect(strays(Object.keys(EVENT_SCHEMAS), [FOLDED, IGNORED])).toEqual({ unowned: [], unknown: [], twice: [] });
  });

  it("are each read by name in the file the table says folds it", () => {
    const missing = Object.entries(FOLDED).filter(([event, file]) => !sourceOf(file).includes(`"${event}"`));
    expect(missing).toEqual([]);
  });
});
