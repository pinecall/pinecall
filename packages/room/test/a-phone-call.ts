/** A phone call's log written by hand: dialled, answered, spoken in, ended, scored — each entry one call. */

import { type Entry } from "../src/wire/envelope.js";

import { CALL } from "./a-room-at-hand.js";
import { BOOKING } from "./a-real-booking.js";

const LINE = { channel: "phone", from: "+34910000000", to: "+34600000001", caller: null };

export function aPhoneLog(): {
  dialing: () => Entry;
  started: () => Entry;
  roomOpened: () => Entry;
  joined: (identity: string, kind: "agent" | "sip") => Entry;
  speaking: (identity: string, speaking: boolean) => Entry;
  ended: (reason: "no_answer" | "agent_hung_up") => Entry;
  scored: () => Entry;
} {
  let seq = 0;
  const entry = (type: string, data: Record<string, unknown>): Entry => {
    seq += 1;
    return { seq, ts: 1_790_000_000 + seq, call: CALL, agent: "clinica", type, ephemeral: false, data };
  };
  return {
    dialing: () => entry("call.dialing", { ...LINE, asked_by: "key_1" }),
    started: () => entry("call.started", { ...LINE, direction: "outbound", started_at: 1_790_000_001 }),
    roomOpened: () => entry("room.opened", { name: CALL, sid: "RM_1", channel: "phone" }),
    joined: (identity, kind) => entry("participant.joined", { identity, kind, attributes: {} }),
    speaking: (identity, speaking) => entry("participant.speaking", { identity, speaking }),
    ended: (reason) =>
      entry("call.ended", { reason, ended_by: reason === "no_answer" ? "platform" : "agent", ended_at: 1_790_000_060, duration_s: 59 }),
    scored: () => entry("call.score", BOOKING.at(-1)?.data ?? {}),
  };
}
