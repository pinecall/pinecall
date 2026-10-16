/** A room on a fake gateway and a fake LiveKit, the way a page would make one, with every state it published kept. */

import { type Entry } from "../src/wire/envelope.js";

import { room, type Code, type Minted, type RoomOptions, type RoomState, type RoomStore } from "../src/room.js";
import { FakeGateway } from "./a-fake-gateway.js";
import { FakeLivekit } from "./a-fake-livekit.js";
import { BOOKING } from "./a-real-booking.js";

export const CALL = "call_1";
export const LOG = `/api/log?call=${CALL}`;
export const MINTED: Minted = { server_url: "wss://lk.example", participant_token: "ticket", call: CALL, log_token: "log_1" };
/** A code as the tenant's server hands it on, and where the page asks the gateway about it. */
export const GW = "https://gw.example";
export const CODE: Code = { code: "4821", number: "+34910000000", expires_at: 1_790_000_600, code_token: "code_1" };
export const ASKED = `${GW}/v1/codes/4821?wait=1&token=code_1`;

export interface AtHand {
  store: RoomStore;
  gateway: FakeGateway;
  livekit: FakeLivekit;
  journal: string[];
  heard: RoomState[];
  skipped: string[];
  minted: string[];
}

export function aRoom(options: Partial<RoomOptions> = {}): AtHand {
  const journal: string[] = [];
  const gateway = new FakeGateway(journal);
  const livekit = new FakeLivekit(journal);
  const heard: RoomState[] = [];
  const skipped: string[] = [];
  const minted: string[] = [];
  const store = room({
    tokens: async (scope) => {
      minted.push(scope);
      journal.push(`tokens ${scope}`);
      return MINTED;
    },
    log: (call) => `/api/log?call=${call}`,
    fetch: gateway.fetch,
    livekit: livekit.load,
    onSkipped: (why) => skipped.push(why),
    ...options,
  });
  store.subscribe((state) => heard.push(state));
  return { store, gateway, livekit, journal, heard, skipped, minted };
}

/** A promise and the hands that settle it, for a step a test wants to hold open. */
export function held<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (why: Error) => void } {
  let resolve: (value: T) => void = () => {};
  let reject: (why: Error) => void = () => {};
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

/** The booking up to the moment the call ended, and from there to the score. */
const ENDED_AT = BOOKING.findIndex((entry) => entry.type === "call.ended");
export const TALKED: readonly Entry[] = BOOKING.slice(0, ENDED_AT);
export const LAST_WORDS: readonly Entry[] = BOOKING.slice(ENDED_AT);
