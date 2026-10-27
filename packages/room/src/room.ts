/** One conversation, as the page sees it: the phases, the verbs, and the seat and the log joined in one store. */
//
// Two things happen at once and they are not the same thing. LiveKit carries the audio and the
// typed lines — the room the visitor joins with a ticket the tenant's own server minted, so the
// org's key never reaches a browser. The call's LOG, read straight from the gateway with the token
// minted beside that ticket for that one call, carries what the agent is actually doing: the turns, every tool it called and what came back, its declared state.
// The log is folded by the protocol's own reducer, so what the page draws is what the console
// draws, from the same bytes. A phone call has no seat at all: the log is the whole of it — and
// when the visitor calls the agent, a code they key on the phone names the call the page follows.

import { initialState } from "./wire/reduce.js";

import { claimOf } from "./code.js";
import { LogFold } from "./log/fold.js";
import { followLog, type Ending } from "./log/follow.js";
import type { SseMessage } from "./log/sse.js";
import { joinSeat, type Seat, type Speaking } from "./seat/join.js";
import { gatewayOf, hangingUp, readingOf } from "./reading.js";
import { loadLivekit, type LivekitModule } from "./seat/livekit.js";
import { hiddenSink } from "./seat/sink.js";
import type { Code, Minted } from "./server/index.js";
import { cell } from "./store.js";
import type { Mode, RoomOptions, RoomState, RoomStore } from "./surface.js";

export type { Code, Minted, Mode, Phase, RoomOptions, RoomState, RoomStore } from "./surface.js";

const LINGER_MS = 60_000;
// A seat asked to close is given this long. A network that has gone does not hold the page up.
const PARTING_MS = 3_000;
const QUIET: Speaking = { agent: false, user: false, level: 0 };
const NO_MICROPHONE = "I could not get to your microphone. Check the browser's permission, or write instead.";
const NO_CALL_ME = "room() was given no callMe: the call is placed by your server";
const NO_EXPECT = "room() was given no expect: the code is asked for by your server";
const NO_LOG_TOKEN = "the server answered no log_token, and room() was given no log to relay it through";

/** One conversation's resources. A new start is a new one; the old one is shut first. */
interface Conversation {
  mode: Mode;
  fold: LogFold;
  seat: Seat | null;
  stopFollow: (() => void) | null;
  /** The asking after a code, while the page is expecting a call. */
  waiting: AbortController | null;
  linger: ReturnType<typeof setTimeout> | null;
  /** Says the visitor hung up at the gateway's door (reading.ts); null until the call has a token to say it with. */
  hangUp: (() => void) | null;
}

/** A room for one visitor. Nothing opens until a verb is called. */
export function room(options: RoomOptions): RoomStore {
  const store = cell<RoomState>(idle());
  const { publish } = store;
  const parting = new Set<() => void>();
  let now: Conversation | null = null;
  let closed = false;

  const busy = (): boolean => ["opening", "expecting", "ringing", "live"].includes(store.state.phase);
  const current = (c: Conversation): boolean => now === c;

  // The follow and the seat down, now. Returns the seat's leaving, for a caller that waits on it.
  const shut = (c: Conversation): Promise<void> => {
    c.stopFollow?.();
    c.stopFollow = null;
    c.waiting?.abort();
    if (c.linger !== null) clearTimeout(c.linger);
    c.linger = null;
    const seat = c.seat;
    c.seat = null;
    return seat === null ? Promise.resolve() : seat.leave().catch(() => undefined);
  };

  // A verb's first move, read from the store and never from a closure: a second click while the
  // first is still opening is nothing, and an old conversation is shut before a new one opens.
  const begin = (mode: Mode): Conversation | null => {
    if (closed || busy()) return null;
    if (now !== null) void shut(now);
    const fold = new LogFold((why) => options.onSkipped?.(why));
    const c: Conversation = { mode, fold, seat: null, stopFollow: null, waiting: null, linger: null, hangUp: null };
    now = c;
    publish({ ...idle(), phase: "opening", mode, connection: "connecting" });
    return c;
  };

  const fail = (c: Conversation, error: string): void => {
    if (!current(c)) return;
    void shut(c);
    publish({ phase: "failed", error, connection: "ended", wantsSound: false, speaking: QUIET, voice: null });
  };

  // The call is over for the visitor. The seat goes now; the log is read a while longer, because
  // the agent's last words, the cost and the score are entries that arrive after the room closed.
  // A seat the visitor left by choice says it hung up, at the door and in the room; any other leaves the call to wait.
  const end = (c: Conversation, parting: (seat: Seat) => Promise<void> = (seat) => seat.leave()): Promise<void> => {
    publish({ phase: "ended", wantsSound: false, speaking: QUIET, voice: null });
    c.waiting?.abort();
    const seat = c.seat;
    c.seat = null;
    if (c.stopFollow !== null && c.linger === null) {
      c.linger = setTimeout(() => {
        c.linger = null;
        c.stopFollow?.();
        c.stopFollow = null;
        publish({ connection: "ended" });
      }, options.linger ?? LINGER_MS);
    }
    return seat === null ? Promise.resolve() : parting(seat).catch(() => undefined);
  };

  const heard = (c: Conversation, message: SseMessage): void => {
    if (c.fold.take(message) === null) return;
    store.paint(() => c.fold.snapshot());
    const { status, room: seats } = c.fold.now;
    const phase = store.state.phase;
    if (status === "ended" && (phase === "opening" || phase === "ringing" || phase === "live")) void end(c);
    // A phone call has no seat to say it was answered: the log does. A seat decides for itself.
    if (c.mode === "phone" && status === "active" && phase === "ringing") publish({ phase: "live" });
    if (c.mode === "phone" && store.state.phase === "live") {
      const speaking = (kinds: string[]): boolean =>
        seats?.participants.some((one) => kinds.includes(one.kind) && one.speaking) ?? false;
      say({ agent: speaking(["agent"]), user: speaking(["caller", "sip"]), level: 0 });
    }
  };

  const ended = (c: Conversation, ending: Ending): void => {
    c.stopFollow = null;
    if (c.linger !== null) clearTimeout(c.linger);
    c.linger = null;
    const phase = store.state.phase;
    const waiting = c.mode === "phone" && (phase === "ringing" || phase === "live");
    if (ending.kind === "refused" && waiting) {
      publish({ connection: "ended", phase: "failed", error: `the log answered ${ending.status}`, speaking: QUIET });
    } else if (ending.kind === "sealed" && c.mode === "phone" && phase === "ringing") {
      publish({ connection: "ended", phase: "ended" });
    } else {
      publish({ connection: "ended" });
    }
  };

  const follow = (c: Conversation, url: string): void => {
    c.stopFollow = followLog(
      url,
      {
        onMessage: (message) => {
          if (current(c)) heard(c, message);
        },
        onConnection: (connection) => {
          if (current(c)) publish({ connection });
        },
        onEnded: (ending) => {
          if (current(c)) ended(c, ending);
        },
      },
      options.fetch ?? fetch,
    );
  };

  const say = (speaking: Speaking): void => {
    const was = store.state.speaking;
    if (was.agent === speaking.agent && was.user === speaking.user && was.level === speaking.level) return;
    publish({ speaking });
  };

  const seated = async (c: Conversation, mode: "talk" | "chat", minted: Minted): Promise<void> => {
    let livekit: LivekitModule;
    try {
      livekit = await (options.livekit ?? loadLivekit)();
    } catch (refused) {
      return fail(c, messageOf(refused));
    }
    if (!current(c) || store.state.phase !== "opening") return;
    let seat: Seat;
    try {
      seat = await joinSeat({
        livekit,
        mode,
        voice: options.voice,
        server_url: minted.server_url,
        participant_token: minted.participant_token,
        sink: hiddenSink(),
        on: {
          disconnected: () => {
            if (!current(c)) return;
            c.seat = null;
            if (busy()) void end(c);
          },
          speaking: (speaking) => {
            if (current(c)) say(speaking);
          },
          wantsSound: (wantsSound) => {
            if (current(c)) publish({ wantsSound });
          },
          voice: (voice) => {
            if (current(c)) publish({ voice });
          },
          ui: (data) => {
            if (current(c)) options.onUi?.(data);
          },
        },
      });
    } catch (refused) {
      return fail(c, mode === "talk" ? NO_MICROPHONE : messageOf(refused));
    }
    // Left, closed or ended by the log while the room was joining: the seat is not wanted.
    if (!current(c) || store.state.phase !== "opening") {
      void seat.leave().catch(() => undefined);
      return;
    }
    c.seat = seat;
    publish({ phase: "live", wantsSound: !seat.canPlaybackAudio() });
  };

  return {
    get state() {
      return store.state;
    },
    subscribe: store.subscribe,

    async start(mode, resume) {
      const c = begin(mode);
      if (c === null) return;
      let minted: Minted;
      try {
        minted = await (resume === undefined ? options.tokens(mode) : options.tokens(mode, resume));
      } catch (refused) {
        return fail(c, messageOf(refused));
      }
      if (!current(c) || store.state.phase !== "opening") return;
      const reading = readingOf(options, minted.call, minted.log_token, minted);
      if (reading === null) return fail(c, NO_LOG_TOKEN);
      c.hangUp = hangingUp(options, minted.call, minted.log_token ?? minted.participant_token);
      publish({ call: minted.call, recording: reading.recording, resume: minted.resume_token ?? "" });
      // The call id exists before the room is joined, so the log is followed from its first entry
      // rather than from wherever the room happened to open.
      follow(c, reading.log);
      await seated(c, mode, minted);
    },

    async event(name, data = {}) {
      const seat = now?.seat ?? null;
      if (store.state.phase !== "live" || seat === null) throw new Error("not in a call");
      await seat.event(name, data);
    },

    async callMe(to) {
      const c = begin("phone");
      if (c === null) return;
      const dial = options.callMe;
      if (dial === undefined) return fail(c, NO_CALL_ME);
      let placed: { call: string; log_token?: string | undefined };
      try {
        placed = await dial(to);
      } catch (refused) {
        return fail(c, messageOf(refused));
      }
      if (!current(c) || store.state.phase !== "opening") return;
      const reading = readingOf(options, placed.call, placed.log_token);
      if (reading === null) return fail(c, NO_LOG_TOKEN);
      if (placed.log_token) c.hangUp = hangingUp(options, placed.call, placed.log_token);
      publish({ call: placed.call, phase: "ringing", recording: reading.recording });
      follow(c, reading.log);
    },

    async byPhone() {
      const c = begin("phone");
      if (c === null) return;
      const ask = options.expect;
      if (ask === undefined) return fail(c, NO_EXPECT);
      let code: Code;
      try {
        code = await ask();
      } catch (refused) {
        return fail(c, messageOf(refused));
      }
      if (!current(c) || store.state.phase !== "opening") return;
      publish({ phase: "expecting", code: { code: code.code, number: code.number, expiresAt: code.expires_at } });
      c.waiting = new AbortController();
      const claim = await claimOf(gatewayOf(options), code, options.fetch ?? fetch, c.waiting.signal);
      // Leaving, closing or failing aborted the asking. A claim is a call already answered: it is live.
      if (claim === null || c.waiting.signal.aborted) return;
      if (claim.kind === "failed") return fail(c, claim.error);
      const reading = readingOf(options, claim.call, claim.log_token ?? undefined);
      if (reading === null) return fail(c, NO_LOG_TOKEN);
      if (claim.log_token) c.hangUp = hangingUp(options, claim.call, claim.log_token);
      publish({ call: claim.call, phase: "live", recording: reading.recording });
      follow(c, reading.log);
    },

    async send(text) {
      if (text.trim() === "") return;
      const seat = now?.seat ?? null;
      if (store.state.phase !== "live" || seat === null) throw new Error("not in a call");
      await seat.send(text);
    },

    async leave() {
      const c = now;
      if (c === null || !busy()) return;
      c.hangUp?.();
      const leaving = end(c, (seat) => seat.hangUp());
      let wake = (): void => {};
      const waited = new Promise<void>((done) => {
        const timer = setTimeout(done, PARTING_MS);
        wake = () => {
          clearTimeout(timer);
          done();
        };
      });
      parting.add(wake);
      await Promise.race([leaving, waited]);
      wake();
      parting.delete(wake);
    },

    playSound() {
      now?.seat?.playSound();
      publish({ wantsSound: false });
    },

    close() {
      if (closed) return;
      closed = true;
      if (now !== null) void shut(now);
      now = null;
      for (const wake of parting) wake();
      parting.clear();
      store.close();
    },
  };
}

function idle(): RoomState {
  return {
    phase: "idle",
    mode: null,
    call: "",
    error: "",
    recording: "",
    log: initialState(),
    entries: [],
    connection: "ended",
    wantsSound: false,
    speaking: QUIET,
    voice: null,
    code: null,
    resume: "",
  };
}

function messageOf(refused: unknown): string {
  return refused instanceof Error ? refused.message : String(refused);
}
