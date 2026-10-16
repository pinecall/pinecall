/** A written call at the agent, wherever it is held: one socket, each line a turn, redialled when the gateway drops it. */

import type { Entry } from "../../api/calls.js";
import { chatUrl, type ChatOpening } from "../../api/calls.js";
import type { Context } from "../../context.js";
import { GatewayError, UsageError } from "../../errors.js";
import { readJsonFile } from "../../kit/json-file.js";

// Reconnect budget: about a minute in total, enough for a gateway restart.
export const BACK_TRIES = 15;
const BACK_FIRST_MS = 500;
const BACK_CAP_MS = 5_000;

/** How long one line waits for the agent to finish answering it. */
export const ANSWERS_WITHIN_MS = 60_000;
// How long a hang-up waits for the gateway to end the call and close the socket.
const HANG_UP_WITHIN_MS = 5_000;
// Time for the call's first entry: register plus first render, no model turn.
const OPENS_WITHIN_MS = 20_000;

/** Lines sent the gateway has not yet taken as a turn, and whether the agent is still answering one. */
export interface Owed {
  lines: number;
  answering: boolean;
}

export const NOTHING_OWED: Owed = { lines: 0, answering: false };

/** One more line sent, not yet heard. */
export function sent(owed: Owed): Owed {
  return { ...owed, lines: owed.lines + 1 };
}

/**
 * What is still owed after one more entry of the call. Lines sent together are taken one turn at a
 * time: each `turn.user` is one of them heard, and the agent listening again is that one answered.
 */
export function owing(owed: Owed, entry: { type?: string; data?: unknown }): Owed {
  if (entry.type === "turn.user") return { lines: Math.max(owed.lines - 1, 0), answering: true };
  const state = entry.type === "agent.state" ? (entry.data as { state?: string } | undefined)?.state : undefined;
  return state === "listening" && owed.answering ? { ...owed, answering: false } : owed;
}

/** Every line sent was heard and answered. */
export function answered(owed: Owed): boolean {
  return owed.lines === 0 && !owed.answering;
}

/** Exponential backoff before the `back`-th reconnect attempt. */
export function waitBack(back: number): number {
  return Math.min(BACK_FIRST_MS * 2 ** (back - 1), BACK_CAP_MS);
}

/** What a chat tells whoever opened it, as it happens. */
export interface ChatListeners {
  /** Every frame of the call: an entry, or an error frame the gateway sent. */
  onEntry?: (entry: Entry, raw: string) => void;
  /** The gateway went away and the call is kept: redialling. */
  onLost?: () => void;
  /** The gateway is back. */
  onBack?: () => void;
}

/** How a chat is opened: the agent, who plays the caller, the state, the process pinned. */
export interface ChatOptions extends Omit<ChatOpening, "app" | "call"> {
  agent: string;
  /** Read on every dial: the app id changes when the process holding the agent restarts. */
  app?: string | undefined | (() => string | undefined);
}

/** The state of case `which` (default 0) in a goldens file; a single object counts as one case. */
export function stateOfCase(file: string, which: number | undefined): Record<string, unknown> {
  const parsed = readJsonFile<{ state?: Record<string, unknown> } | { state?: Record<string, unknown> }[]>("--state", file);
  const cases = Array.isArray(parsed) ? parsed : [parsed];
  const chosen = cases[which ?? 0];
  if (chosen === undefined) throw new UsageError(`${file} has no case ${which ?? 0}`);
  return chosen.state ?? {};
}

/**
 * One written call. The key goes in the Authorization header (the global WebSocket cannot set
 * headers, hence `ws`, loaded only here). An unexpected close is a gateway restart: redialled with
 * `?call=` to resume, until the budget runs out or the call is over.
 */
export class Chat {
  /** The call's id, once the first entry named it. */
  call: string | null = null;
  /** The call ended (the agent hung up, the gateway closed it, or we did). */
  ended = false;
  private over = false;
  private owed: Owed = NOTHING_OWED;
  private back = 0;
  private leaving = false;
  private socket: import("ws").WebSocket | null = null;
  private waiting: (() => void) | undefined;
  private readonly closed: Promise<string>;
  private closedWith!: (why: string) => void;

  private constructor(
    private readonly ctx: Context,
    private readonly options: ChatOptions,
    private readonly listeners: ChatListeners,
    private readonly WebSocket: typeof import("ws").WebSocket,
  ) {
    this.closed = new Promise((done) => (this.closedWith = done));
  }

  /** Dial the agent; resolves once the call has an id, rejects with the gateway's refusal. */
  static async open(ctx: Context, options: ChatOptions, listeners: ChatListeners = {}): Promise<Chat> {
    const { WebSocket } = await import("ws");
    const chat = new Chat(ctx, options, listeners, WebSocket);
    await chat.dial(true);
    return chat;
  }

  /** Say a line; the gateway takes it as one turn. */
  say(text: string): void {
    if (this.socket?.readyState === this.WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ text }));
      this.owed = sent(this.owed);
    }
  }

  /** Say a line and wait until it was heard and answered whole, or the call ended, or the wait is up. */
  async sayAndWait(text: string, withinMs = ANSWERS_WITHIN_MS): Promise<void> {
    if (this.ended) throw new UsageError("this call has ended: open another");
    this.say(text);
    await this.untilAnswered(withinMs);
  }

  /** Whether every line sent was heard and answered. */
  get settled(): boolean {
    return answered(this.owed);
  }

  /** Wait until nothing is owed, or the call ended, or the wait is up. */
  untilAnswered(withinMs = ANSWERS_WITHIN_MS): Promise<void> {
    if (this.ended || answered(this.owed)) return Promise.resolve();
    return new Promise((done) => {
      const late = setTimeout(() => {
        this.waiting = undefined;
        done();
      }, withinMs);
      this.waiting = () => {
        if (!this.ended && !answered(this.owed)) return;
        clearTimeout(late);
        this.waiting = undefined;
        done();
      };
    });
  }

  /** Hang up: the gateway ends the call and closes the socket; a gateway that never closes is left. */
  async end(): Promise<string> {
    this.leaving = true;
    if (this.socket?.readyState !== this.WebSocket.OPEN) {
      this.socket?.close();
      return this.closed;
    }
    this.socket.send(JSON.stringify({ hangup: true }));
    const hungUp = this.socket;
    setTimeout(() => hungUp.close(), HANG_UP_WITHIN_MS).unref();
    return this.closed;
  }

  /** Resolves with the close reason ("" for a clean end) once the call is over for us. */
  done(): Promise<string> {
    return this.closed;
  }

  private dial(first: boolean): Promise<void> {
    return new Promise((opened, refused) => {
      const app = typeof this.options.app === "function" ? this.options.app() : this.options.app;
      const url = chatUrl(this.ctx.gateway(), this.options.agent, { ...this.options, app, call: this.call ?? undefined });
      const socket = new this.WebSocket(url, { headers: this.ctx.gateway().headers() });
      this.socket = socket;
      let settled = false;
      const giveUp = first ? setTimeout(() => settle(() => refused(new GatewayError(502, "the gateway took the socket but wrote no entry: nothing to read"))), OPENS_WITHIN_MS) : undefined;
      const settle = (how: () => void): void => {
        if (settled) return;
        settled = true;
        clearTimeout(giveUp);
        how();
      };
      socket.on("message", (frame: Buffer) => {
        const raw = frame.toString();
        const entry = entryOf(raw);
        // Reset retries on the first message, not on open: the gateway may accept and then refuse.
        if (this.back > 0) this.listeners.onBack?.();
        this.back = 0;
        if (typeof entry.call === "string") this.call = entry.call;
        if (entry.type === "call.score") this.over = true;
        this.owed = owing(this.owed, entry);
        settle(() => opened());
        this.listeners.onEntry?.(entry, raw);
        this.waiting?.();
      });
      // An error is followed by a close, and the close decides.
      socket.on("error", () => undefined);
      socket.on("close", (_code: number, reason: Buffer) => {
        const why = reason.toString();
        if (this.call === null) {
          settle(() => refused(new GatewayError(502, why === "" ? "the gateway closed the call before it opened" : why)));
          this.finish(why);
          return;
        }
        // A redial that closed again settles its own promise; whether to dial once more is decided below.
        settle(() => opened());
        if (this.leaving || this.over || this.back >= BACK_TRIES) {
          this.finish(this.leaving || this.over ? "" : why);
          return;
        }
        // A close reason while reconnecting may just mean the app socket has not re-registered yet.
        if (this.back === 0) this.listeners.onLost?.();
        this.back += 1;
        setTimeout(() => void this.dial(false).catch(() => undefined), waitBack(this.back));
      });
    });
  }

  private finish(why: string): void {
    this.ended = true;
    this.waiting?.();
    this.closedWith(why);
  }
}

// A frame that is no entry is heard as an error, never thrown: a throw in a socket's handler would end the process.
function entryOf(raw: string): Entry {
  try {
    const parsed = JSON.parse(raw) as Partial<Entry>;
    return { seq: parsed.seq ?? 0, type: parsed.type ?? "", data: parsed.data ?? {}, call: parsed.call ?? null, ...(parsed.ts === undefined ? {} : { ts: parsed.ts }) };
  } catch {
    return { seq: 0, type: "error", data: { message: `the gateway sent a frame that is no entry: ${raw.slice(0, 80)}` } };
  }
}
