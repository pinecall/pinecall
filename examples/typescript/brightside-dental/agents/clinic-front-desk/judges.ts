import { ownJudge } from "@pinecall/agents";

// A judge asks one question of every call when it ends, and answers held or broken.
// `consent` and `grounded` are Pinecall's; this one is the clinic's own.

export const offersARealTime = ownJudge({
  name: "offers-a-real-time",
  asks: "Did every time the agent offered come from a freeSlots result of this call?",
  reads: ["evidence"],
});
