/** `this.call`: the live call an agent instance serves — its room, turns and verbs. */

import { type Medium } from "../wire/defs.js";

import type { Call as HookCall } from "../agent/lifecycle.js";
import { History } from "./history.js";
import { ParticipantHandle, Room, type Commander, type ParticipantKind } from "./room.js";

/** How long `say`/`reply` wait for their `turn.agent` before resolving false. */
const ACK_MS = 30_000;

/** Transfer timeout: the far end may ring for 25s before it fails. */
const TRANSFER_MS = 90_000;

/** Extra time `attention()` waits beyond `waitS` for the answer entry to arrive. */
const A_MOMENT_MS = 15_000;

/** Error when no answer came back: the gateway, not the far end, went quiet. */
const NO_ANSWER = "the runtime never said how it went";

/** Error for a pending verb when the call ends first. */
const THE_CALL_ENDED = "the call ended before it was answered";

/** `cold`: the caller is sent on. `warm`: the far end is dialled into the call. */
export type TransferMode = "cold" | "warm";

/** The supervisor who took the line, as their token names them. */
export interface Supervisor {
  id: string;
  name?: string;
}

/** Result of `transfer()`. `ok: false` means the caller is still on the line. */
export interface Transferred {
  to: string;
  mode: TransferMode | null;
  ok: boolean;
  error?: string;
}

/** Result of `attention()`: who took the line, or why nobody did. */
export interface Attended {
  ok: boolean;
  by: Supervisor | null;
  error?: string;
}

/** One search hit: its source path, heading and text. */
export interface Found {
  path: string;
  heading: string | null;
  text: string;
}

/** Runs a search for this call through the gateway. */
export type Searching = (query: string, k?: number) => Promise<Found[]>;

/** Error for `search()` on a call with no gateway (an offline prompt, a test). */
export const NO_GATEWAY_TO_SEARCH = "this call cannot search: no gateway is serving it";

/** Line facts the call needs beyond what the room's entries carry. */
export interface CallLine extends HookCall {
  today?: string;
  claimed?: string | null;
}

/**
 * One live call. State is reduced from log entries; every verb sends one wire command.
 * There is no direct LiveKit access.
 */
export class CallWorld implements HookCall {
  readonly id: string;
  readonly contact: string;
  readonly from?: string;
  readonly channel?: string;
  /** Spoken (`voice`) or written (`text`). A gateway that does not say gets it from the channel. */
  readonly medium: Medium;
  /** The day this call opened, `YYYY-MM-DD`. */
  readonly today?: string;
  /** The page code this call claimed, or null. */
  claimed: string | null = null;
  readonly room: Room;
  readonly history = new History();

  // say/reply settle on the next turn.agent: commands are fire-and-forget, so that entry is the only ack.
  #speaking: ((spoken: boolean) => void)[] = [];
  // Settled by call.transferred and attention.answered.
  #transfers: ((transferred: Transferred) => void)[] = [];
  #asks: ((attended: Attended) => void)[] = [];
  /** The event being dispatched, so a write inside onEvent can name its cause. */
  cause: { name: string; seq: number } | null = null;
  #events = 0;

  constructor(
    line: CallLine,
    private readonly out: Commander,
    private readonly searching: Searching | null = null,
    private readonly ackMs = ACK_MS,
  ) {
    this.id = line.id;
    this.contact = line.contact;
    if (line.from !== undefined) this.from = line.from;
    if (line.channel !== undefined) this.channel = line.channel;
    this.medium = line.medium ?? (line.channel === "whatsapp" ? "text" : "voice");
    if (line.today !== undefined) this.today = line.today;
    if (line.claimed !== undefined) this.claimed = line.claimed;
    this.room = new Room(out);
  }

  /** Next sequence number for this call's events (independent of the wire's seq). */
  numbered(): number {
    return (this.#events += 1);
  }

  /** A handle to one participant, e.g. `call.participant(id).mute()`. */
  participant(identity: string): ParticipantHandle {
    return new ParticipantHandle(identity, this.out);
  }

  /** Send a payload to browsers in the room. The log records its size, not its content. */
  send(topic: string, data: Record<string, unknown>, options: { to?: string } = {}): void {
    this.out("room.send", options.to === undefined ? { topic, data } : { topic, data, to: options.to });
  }

  /** Speak this text verbatim. Resolves true once the turn lands, false on timeout. */
  say(text: string, options: { allowInterruptions?: boolean } = {}): Promise<boolean> {
    this.out("agent.say", { text, ...options });
    return this.#spoken();
  }

  /** Have the model speak, guided by instructions the caller never hears. Resolves like `say`. */
  reply(instructions: string, options: { allowInterruptions?: boolean } = {}): Promise<boolean> {
    this.out("agent.reply", { instructions, ...options });
    return this.#spoken();
  }

  /**
   * Search the knowledge bases attached to this agent. The gateway runs the search and logs the
   * results. `k` defaults to each base's own setting.
   */
  search(query: string, options: { k?: number } = {}): Promise<Found[]> {
    if (this.searching === null) return Promise.reject(new Error(NO_GATEWAY_TO_SEARCH));
    return this.searching(query, options.k);
  }

  /** Invite someone into the room. Same as `room.invite`. */
  invite(to: string, options: { kind: "sip" | "participant" }): void {
    this.room.invite(to, options);
  }

  /**
   * Transfer the caller to a number. On a phone call the line is sent on (cold); in a browser the
   * number is dialled into the call (warm) and the agent goes silent once it answers. `mode`
   * forces one. `ok: false` means the caller is still with the agent.
   */
  transfer(to: string, options: { mode?: TransferMode } = {}): Promise<Transferred> {
    this.out("call.transfer", options.mode === undefined ? { to } : { to, mode: options.mode });
    return this.#answered(this.#transfers, TRANSFER_MS, { to, mode: null, ok: false, error: NO_ANSWER });
  }

  /**
   * Ask for a supervisor. The caller waits (on hold, or unanswered in a thread) until someone takes
   * the line or `waitS` passes. `reason` is shown to the supervisor. The calling tool runs the
   * whole time, so give it a `timeout` longer than `waitS`.
   */
  attention(reason: string, options: { waitS: number }): Promise<Attended> {
    this.out("call.attention", { reason, waitS: options.waitS });
    const lapsed: Attended = { ok: false, by: null, error: NO_ANSWER };
    return this.#answered(this.#asks, options.waitS * 1000 + A_MOMENT_MS, lapsed);
  }

  /** Put the caller on hold: they hear hold music and the agent neither speaks nor listens. */
  hold(): void {
    this.out("call.hold", {});
  }

  /** Take the caller off hold. */
  unhold(): void {
    this.out("call.unhold", {});
  }

  /** Send DTMF tones: `0-9`, `*`, `#`, and `,` for a pause. */
  dtmf(digits: string): void {
    this.out("call.dtmf", { digits });
  }

  /**
   * Bind this call to the code shown on the caller's page, so the page follows the call. Sets
   * `claimed` on `call.claimed`; an unknown, expired or taken code is refused with `no_code`.
   */
  claim(code: string): void {
    this.out("call.claim", { code });
  }

  /** Record a callback request in the call log for your backend to dial. */
  callback(number: string, options: { when?: string; note?: string } = {}): void {
    this.out("call.callback", { number, ...options });
  }

  /**
   * The caller asked never to be called again: their number joins the org's do-not-call list, and
   * no call of the org reaches it until a consent is recorded. Tell them it is done.
   */
  optOut(note?: string): void {
    this.out("call.opt_out", note === undefined ? {} : { note });
  }

  /** End the call. Say goodbye before calling this; nothing after it is heard. */
  hangup(reason?: string): void {
    this.out("call.hangup", reason === undefined ? {} : { reason });
  }

  /** Fold one log entry into the room and history. Unknown types are ignored. */
  take(type: string, data: Record<string, unknown>, at: number): void {
    switch (type) {
      case "participant.joined":
        return this.room.joined(
          {
            identity: String(data["identity"]),
            kind: data["kind"] as ParticipantKind,
            ...(typeof data["name"] === "string" ? { name: data["name"] } : {}),
          },
          at,
        );
      case "call.claimed":
        this.claimed = String(data["code"]);
        return;
      case "participant.left":
        return this.room.left(String(data["identity"]));
      case "participant.speaking":
        return this.room.speaking(String(data["identity"]), data["speaking"] === true);
      case "turn.user":
        return this.history.took({ who: "user", text: String(data["text"] ?? ""), speechId: String(data["speech_id"] ?? data["speechId"] ?? ""), interrupted: false, at });
      case "turn.agent":
        this.history.took({ who: "agent", text: String(data["text"] ?? ""), speechId: String(data["speech_id"] ?? data["speechId"] ?? ""), interrupted: data["interrupted"] === true, at });
        return this.#settle(true);
      case "call.transferred":
        return settle(this.#transfers, {
          to: String(data["to"] ?? ""),
          mode: (data["mode"] ?? null) as TransferMode | null,
          ok: data["ok"] === true,
          ...(typeof data["error"] === "string" ? { error: data["error"] } : {}),
        });
      case "attention.answered":
        return settle(this.#asks, {
          ok: data["ok"] === true,
          by: (data["by"] ?? null) as Supervisor | null,
          ...(typeof data["error"] === "string" ? { error: data["error"] } : {}),
        });
      // Settle every pending verb now instead of waiting for its timeout.
      case "call.ended":
        this.#settle(false);
        settle(this.#transfers, { to: "", mode: null, ok: false, error: THE_CALL_ENDED });
        settle(this.#asks, { ok: false, by: null, error: THE_CALL_ENDED });
        return;
      default:
        return;
    }
  }

  #spoken(): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      this.#speaking.push(resolve);
      // Resolve false rather than reject: a hang-up mid-sentence is not an error the tool can handle.
      setTimeout(() => {
        this.#speaking = this.#speaking.filter((waiting) => waiting !== resolve);
        resolve(false);
      }, this.ackMs).unref?.();
    });
  }

  #settle(spoken: boolean): void {
    const waiting = this.#speaking;
    this.#speaking = [];
    for (const resolve of waiting) resolve(spoken);
  }

  // The runtime always answers via a log entry; the ceiling only guards against a gateway that went away.
  #answered<T>(waiting: ((answer: T) => void)[], ceiling: number, lapsed: T): Promise<T> {
    return new Promise<T>((resolve) => {
      waiting.push(resolve);
      setTimeout(() => {
        const index = waiting.indexOf(resolve);
        if (index >= 0) waiting.splice(index, 1);
        resolve(lapsed);
      }, ceiling).unref?.();
    });
  }
}

function settle<T>(waiting: ((answer: T) => void)[], answer: T): void {
  const resolvers = waiting.splice(0, waiting.length);
  for (const resolve of resolvers) resolve(answer);
}
