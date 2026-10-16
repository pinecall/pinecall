/** Folds a log into its State, entry by entry, as the runtime's reducer does. */

import { type Event, eventOf } from "./codec.js";
import { type Entry } from "./envelope.js";
import { type ParticipantJoined } from "./room.js";
import { type Confirm, type Participant, type State, type ToolRun } from "./state.js";

/** Fold every entry, in the order given, into the state an empty log starts from. */
export function reduce(entries: Iterable<Entry>): State {
  let state = initialState();
  for (const entry of entries) {
    state = apply(state, entry);
  }
  return state;
}

/** The state of an empty log: nothing known, every list empty, status idle. */
export function initialState(): State {
  return {
    seq: 0,
    agent: "",
    call: null,
    status: "idle",
    channel: null,
    direction: null,
    from: null,
    to: null,
    caller: null,
    room: null,
    started_at: null,
    ended_at: null,
    end_reason: null,
    outcome: null,
    user_state: null,
    agent_state: null,
    live: { user: null, agent: null },
    turns: [],
    metrics: { llm: [], stt: [], tts: [], vad: [], eou: [], eot: [], interruption: [], realtime: [], avatar: [] },
    tools: [],
    app_state: {},
    events: [],
    prompt: {},
    tools_visible: [],
    confirms: [],
    memory: [],
    sources: [],
    handoff: { active: false, by: null },
    held: false,
    muted: false,
    transfer: null,
    attention: null,
    usage: [],
    cost: null,
    routes: [],
    gaps: [],
    errors: [],
    custom: [],
  };
}

/** Error code recorded for an entry the reader cannot decode. */
export const UNREADABLE = "unreadable";

// Old logs may hold entries in shapes this reader no longer accepts. Record one error and keep
// folding instead of rejecting the whole call, as the runtime does.
function unreadable(state: State, entry: Entry, why: unknown): State {
  const said = why instanceof Error ? why.message : String(why);
  state.errors.push({
    seq: entry.seq,
    code: UNREADABLE,
    message: `${entry.type} at seq ${entry.seq} is not the shape this reader knows: ${
      said.split("\n")[0]?.trim() ?? said
    }`,
  });
  return state;
}

// A gap with a snapshot replaces the state; every other entry mutates it in place. The seq always
// advances to the entry's.
/** Fold one entry in and return the state to continue with. */
export function apply(state: State, entry: Entry): State {
  let event: Event;
  try {
    event = eventOf(entry);
  } catch (why) {
    const said = unreadable(state, entry, why);
    said.seq = entry.seq;
    said.agent = entry.agent;
    if (entry.call !== null) {
      said.call = entry.call;
    }
    return said;
  }
  let next = state;
  if (event.type === "log.gap") {
    next = onLogGap(state, event);
  } else {
    applyEvent(state, entry, event);
  }
  next.seq = entry.seq;
  next.agent = entry.agent;
  if (entry.call !== null) {
    next.call = entry.call;
  }
  return next;
}

function applyEvent(state: State, entry: Entry, event: Event): void {
  switch (event.type) {
    // ── the call ──
    case "call.ringing":
      state.status = "ringing";
      state.direction = "inbound";
      rememberTheLine(state, event.data);
      return;
    case "call.dialing":
      state.status = "dialing";
      state.direction = "outbound";
      rememberTheLine(state, event.data);
      return;
    case "call.started":
      state.status = "active";
      state.direction = event.data.direction;
      state.started_at = event.data.started_at;
      rememberTheLine(state, event.data);
      return;
    case "call.ended":
      state.status = "ended";
      state.ended_at = event.data.ended_at;
      state.end_reason = event.data.reason;
      state.live = { user: null, agent: null };
      // A caller who hung up while waiting for a person was never answered.
      if (state.attention?.status === "open") state.attention = { ...state.attention, status: "lapsed" };
      return;
    case "call.transferred":
      state.transfer = {
        to: event.data.to,
        mode: event.data.mode,
        status: event.data.ok ? "done" : "failed",
        by: state.transfer?.by ?? "agent",
      };
      return;
    case "call.line":
      state.held = event.data.held;
      state.muted = event.data.muted;
      return;
    case "call.summary":
      state.usage = [...event.data.usage];
      state.cost = event.data.cost;
      state.outcome = event.data.outcome;
      state.end_reason ??= event.data.reason;
      return;
    // ── the conversation ──
    case "user.state":
      state.user_state = event.data.state;
      return;
    case "agent.state":
      state.agent_state = event.data.state;
      return;
    case "user.transcript":
      state.live.user = event.data.final ? null : event.data.text;
      return;
    case "agent.transcript":
      // A delta: one word of a spoken reply, or one token of a written one.
      state.live.agent = event.data.final ? null : saidSoFar(state.live.agent, event.data);
      return;
    case "turn.user":
      state.turns.push({ role: "user", ...event.data });
      state.live.user = null;
      return;
    case "turn.agent":
      state.turns.push({ role: "agent", ...event.data });
      state.live.agent = null;
      return;
    case "memory.ops":
      state.memory.push(...event.data.ops);
      return;
    case "docs.sources":
      state.sources = [...event.data.sources];
      return;
    // ── metrics: every block is kept, in order, by kind ──
    case "metrics.llm":
      state.metrics.llm.push(event.data);
      return;
    case "metrics.stt":
      state.metrics.stt.push(event.data);
      return;
    case "metrics.tts":
      state.metrics.tts.push(event.data);
      return;
    case "metrics.vad":
      state.metrics.vad.push(event.data);
      return;
    case "metrics.eou":
      state.metrics.eou.push(event.data);
      return;
    case "metrics.eot":
      state.metrics.eot.push(event.data);
      return;
    case "metrics.interruption":
      state.metrics.interruption.push(event.data);
      return;
    case "metrics.realtime":
      state.metrics.realtime.push(event.data);
      return;
    case "metrics.avatar":
      state.metrics.avatar.push(event.data);
      return;
    // ── tools, state, confirmation ──
    case "tool.call":
      state.tools.push({ ...event.data, status: "running", seq: entry.seq });
      return;
    case "tool.result":
      onToolResult(state, event.data);
      return;
    case "state.changed":
      state.app_state = { ...event.data.state };
      return;
    case "prompt.changed":
      state.prompt[event.data.name] = { hash: event.data.hash, chars: event.data.chars, seq: entry.seq };
      return;
    case "tools.changed":
      state.tools_visible = [...event.data.visible];
      return;
    case "confirm.request":
      state.confirms.push({
        tool: event.data.tool,
        call_id: event.data.call_id,
        audience: event.data.audience,
        phrase: event.data.phrase,
        status: "pending",
      });
      return;
    case "confirm.granted":
      settleConfirm(state, event.data.call_id, { status: "granted", said: event.data.said });
      return;
    case "confirm.declined":
      settleConfirm(state, event.data.call_id, {
        status: "declined",
        reason: event.data.reason,
        ...(event.data.said !== undefined ? { said: event.data.said } : {}),
      });
      return;
    // ── supervision, the agent, markers ──
    case "supervisor.took_over":
      state.handoff = { active: true, by: event.data.by };
      return;
    case "supervisor.released":
      state.handoff = { active: false, by: null };
      return;
    case "supervisor.transferred":
      state.transfer = { to: event.data.to, mode: event.data.mode, status: "requested", by: "supervisor" };
      return;
    case "attention.requested":
      state.attention = { reason: event.data.reason, wait_s: event.data.wait_s, status: "open", asked_at: entry.ts, by: null };
      return;
    case "attention.answered":
      if (state.attention !== null && state.attention !== undefined) {
        state.attention = { ...state.attention, status: event.data.ok ? "answered" : "lapsed", by: event.data.by };
      }
      return;
    case "agent.registered":
      state.routes = [...event.data.routes];
      return;
    case "error":
      state.errors.push({ seq: entry.seq, code: event.data.code, message: event.data.message });
      return;
    case "custom":
      state.custom.push({ seq: entry.seq, name: event.data.name, data: { ...event.data.data } });
      return;
    // ── the room and the outside world ──
    case "room.opened":
      state.room = { name: event.data.name, sid: event.data.sid, participants: [], caller: null };
      return;
    case "participant.joined":
      onParticipantJoined(state, entry, event.data);
      return;
    case "participant.left":
      onParticipantLeft(state, event.data.identity);
      return;
    case "participant.speaking": {
      const who = participantIn(state, event.data.identity);
      if (who !== undefined) {
        who.speaking = event.data.speaking;
      }
      return;
    }
    // The fact is kept by name and origin; its data stays in the log at that seq.
    case "event.received": {
      const { data: _data, ...fact } = event.data;
      state.events.push({ ...fact, seq: entry.seq });
      return;
    }
    // Not reduced: supervisor.said/.whispered surface as turns and prompt changes, supervisor.ended
    // as call.ended, and the rest are kept in the log only.
    case "track.published":
    case "track.unpublished":
    case "room.sent":
    case "supervisor.said":
    case "supervisor.whispered":
    case "supervisor.ended":
    case "agent.configured":
    case "pong":
    case "log.caught_up":
    case "log.gap":
      return;
  }
}

function rememberTheLine(
  state: State,
  line: { channel: State["channel"]; from: string; to: string; caller: State["caller"] },
): void {
  state.channel = line.channel;
  state.from = line.from;
  state.to = line.to;
  state.caller = line.caller;
}

function onToolResult(state: State, result: Event & { type: "tool.result" } extends { data: infer D } ? D : never): void {
  const index = lastIndex(state.tools, (run) => run.call_id === result.call_id);
  if (index === -1) {
    return;
  }
  const { call_id: _callId, name: _name, ...outcome } = result;
  const run = state.tools[index] as ToolRun;
  state.tools[index] = { ...run, ...outcome, status: outcome.error !== undefined ? "failed" : "done" };
}

function settleConfirm(state: State, callId: string, verdict: Partial<Confirm>): void {
  const index = lastIndex(state.confirms, (confirm) => confirm.call_id === callId);
  if (index === -1) {
    return;
  }
  const confirm = state.confirms[index] as Confirm;
  state.confirms[index] = { ...confirm, ...verdict };
}

// joined_at is the entry's ts; the event does not repeat it.
function onParticipantJoined(state: State, entry: Entry, joined: ParticipantJoined): void {
  if (state.room === null) {
    return;
  }
  state.room.participants.push({ ...joined, joined_at: entry.ts, speaking: false });
  if (joined.kind === "caller") {
    state.room.caller = joined.identity;
  }
}

// An identity is unique within a room: LiveKit disconnects the first of two that share one.
function onParticipantLeft(state: State, identity: string): void {
  if (state.room === null) {
    return;
  }
  const seat = state.room.participants.findIndex((one) => one.identity === identity);
  if (seat !== -1) {
    state.room.participants.splice(seat, 1);
  }
  if (state.room.caller === identity) {
    state.room.caller = null;
  }
}

function participantIn(state: State, identity: string): Participant | undefined {
  return state.room?.participants.find((one) => one.identity === identity);
}

function onLogGap(state: State, event: Event & { type: "log.gap" }): State {
  const next = event.data.snapshot !== null ? structuredClone(event.data.snapshot) : state;
  next.gaps.push({ from_seq: event.data.from_seq, to_seq: event.data.to_seq });
  return next;
}

function lastIndex<T>(items: T[], matches: (item: T) => boolean): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (matches(items[index] as T)) {
      return index;
    }
  }
  return -1;
}

/**
 * Append a delta to the reply in flight. Aligned voice words arrive bare and are joined with a
 * space; written tokens carry their own spacing ("clean" + "ing" must not gain a space).
 */
function saidSoFar(soFar: string | null, delta: { text: string; start?: number | null | undefined }): string {
  if (soFar === null || soFar === "") return delta.text;
  const apart = /\s$/.test(soFar) || /^\s/.test(delta.text);
  return delta.start != null && !apart ? `${soFar} ${delta.text}` : `${soFar}${delta.text}`;
}
