// The judges and the callers of {{Title}}'s own, as code: imported by agent.tsx into the `judges` and the `personas` of its @agent({ … }).

import { ownPersona } from "@pinecall/agents";

// A judge of the agent's own asks one question of every call at hang-up, answered held or broken; `pinecall judges try
// <name> --last 5` asks it of the last calls before you keep it. One looks like this:
//   export const messageTaken = ownJudge({ name: "message-taken", asks: "Did the agent write the message down before saying goodbye?" });

/** Calls from the street, in a rush, with one thing to leave. */
export const hurried = ownPersona({
  name: "hurried",
  about: "Calls from the street, in a rush, with one thing to leave",
  goal: "leave a message for the business: I am Ana García and the delivery for tomorrow has to come after 4 pm",
  style: "short sentences, interrupts, gives one fact at a time, asks twice whether the message is written down",
  facts: { "their name": "Ana García", "their phone": "600 000 001" },
  expects: ["The agent should write the message down with the caller's name and what it is about.", "The agent should not promise when the business will call back."],
  behavior: { interrupts: 0.3, pauseS: 1 },
});
