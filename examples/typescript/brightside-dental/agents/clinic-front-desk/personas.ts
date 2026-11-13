import { ownPersona } from "@pinecall/agents";

// A test caller: who they are, what they want and how they talk. `pinecall simulate` phones the
// agent as each one, and the judges read the call.

export const hurried = ownPersona({
  name: "hurried",
  goal: "I want a cleaning this Thursday morning, the earliest time you have",
  style: "short sentences, interrupts, gives my name only when asked",
  expects: ["The agent should offer times from the agenda and book the one I choose."],
});

export const chargedTwice = ownPersona({
  name: "charged-twice",
  goal: "I was charged twice for last month's cleaning and I want one charge back",
  style: "polite, a little annoyed, has the invoice number at hand",
  expects: ["The agent should pass me to billing, and never promise a refund itself."],
});
