/** What a room is to the page: its phases, the state it publishes, the options it takes and its verbs. */

import { type Entry } from "./wire/envelope.js";
import { type State } from "./wire/state.js";

import type { Connection } from "./log/follow.js";
import type { Speaking } from "./seat/join.js";
import type { LivekitModule } from "./seat/livekit.js";
import type { Code, Minted } from "./server/index.js";
import type { Store } from "./store.js";

export type { Code, Minted };

/** Where the conversation is. `ringing`: a phone call nobody answered yet; `expecting`: a code no call claimed yet. */
export type Phase = "idle" | "opening" | "expecting" | "ringing" | "live" | "ended" | "failed";

/** Spoken, written, or on the visitor's own phone. The same agent every way. */
export type Mode = "talk" | "chat" | "phone";

/** Everything the page draws from. Every field is the truth at the moment it was published. */
export interface RoomState {
  phase: Phase;
  mode: Mode | null;
  call: string;
  /** The sentence to show when phase is "failed". */
  error: string;
  /** Where the call's recording plays from once it has ended, or "" when the log is relayed. */
  recording: string;
  /** The call as the protocol folds it: turns, tools, the agent's state, the cost once it is known. */
  log: State;
  entries: Entry[];
  connection: Connection;
  /** True when the browser has not been told it may make a sound: ask for a click. */
  wantsSound: boolean;
  speaking: Speaking;
  /** The element the agent's voice plays in, for a page that listens to it; null outside a spoken call. */
  voice: HTMLMediaElement | null;
  /** The code to show beside the number to call, from `expecting` on; `expiresAt` in seconds since the epoch. */
  code: { code: string; number: string; expiresAt: number } | null;
  /** What to keep to resume this conversation later with `start(mode, resume)`; "" when the gateway gave none. */
  resume: string;
}

export interface RoomOptions {
  /** A ticket for a seat, from the tenant's own server. The page never holds a key. `resume` is the
   * token a resumed conversation was kept with: the server sends it on as `resume` in its mint. */
  tokens: (scope: "talk" | "chat", resume?: string) => Promise<Minted>;
  /** The gateway the log is read from with the call's own token. Default `https://cloud.pinecall.io`. */
  gateway?: string | undefined;
  /** The URL the call's log is relayed at by the tenant's server, for a page that must not reach
   * the gateway itself. Given, the log token is not used. */
  log?: ((call: string, minted?: Minted) => string) | undefined;
  /** Ask the tenant's server to have the agent call `to`: the call, and its log token. */
  callMe?: ((to: string) => Promise<{ call: string; log_token?: string | undefined }>) | undefined;
  /** Ask the tenant's server for a code the visitor keys when they call the agent's number. */
  expect?: (() => Promise<Code>) | undefined;
  /** How long the log is read after the seat closes, waiting for the score. Default 60 000 ms: a worker
   * notices a caller has gone some twenty seconds after the fact, and the score comes after that. */
  linger?: number | undefined;
  fetch?: typeof fetch | undefined;
  livekit?: (() => Promise<LivekitModule>) | undefined;
  /** An entry of the log this copy of the wire could not read. The rest of the call still draws. */
  onSkipped?: ((why: string) => void) | undefined;
  /** What the agent put on the visitor's screen with `call.send("pinecall.ui", data)`, as it sent it. */
  onUi?: ((data: unknown) => void) | undefined;
}

export interface RoomStore extends Store<RoomState> {
  /** A new conversation; with `resume`, the one kept under it: the same call while it still waits for
   * the visitor, else a new call whose agent opens on what was said. */
  start(mode: "talk" | "chat", resume?: string): Promise<void>;
  send(text: string): Promise<void>;
  /** Tell the agent what the visitor did on the page. Its `onEvent(name, data)` runs when its class
   * accepts `name` from a participant; any other name is dropped by the runtime. */
  event(name: string, data?: Record<string, unknown>): Promise<void>;
  callMe(to: string): Promise<void>;
  byPhone(): Promise<void>;
  leave(): Promise<void>;
  playSound(): void;
}
