// The front desk's own judge and its own test caller, declared beside the class.

import { ownJudge, ownPersona } from "@pinecall/agents";

/** Asked of every call: a time the agent says must have come from the agenda. */
export const offersARealTime = ownJudge({
  name: "offers-a-real-time",
  asks: "Did every time the agent offered come from a freeSlots result of this call?",
  reads: ["evidence"],
});

/** A caller in a hurry, for `pinecall simulate`. */
export const hurried = ownPersona({
  name: "hurried",
  goal: "I want a cleaning this Thursday morning, the earliest time you have",
  style: "short sentences, interrupts, gives my name only when asked",
  expects: ["The agent should offer times from the agenda and book the one I choose."],
});
