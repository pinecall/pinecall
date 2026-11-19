// The judges of {{Title}}'s own, as code: imported by agent.tsx into the `judges` of its @agent({ … }).

// A judge of the agent's own asks one question of every call at hang-up, answered held or broken; `pinecall judges try
// <name> --last 5` asks it of the last calls before you keep it. One looks like this, with `ownJudge` imported from
// "@pinecall/agents":
//   export const messageTaken = ownJudge({ name: "message-taken", asks: "Did the agent write the message down before saying goodbye?" });
