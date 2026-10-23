# The smallest app that works

The app socket of [gateway-api.md](gateway-api.md), spoken with no Pinecall package at all.

```js
import WebSocket from "ws";

// Your org's own slug for the agent: a slug is one org's, and another org's is refused.
const AGENT = "clinica-norte";
const FREE_SLOTS = {
  name: "freeSlots",
  description: "Las horas libres de un día. Úsala antes de ofrecer una hora.",
  parameters: { type: "object", properties: { day: { type: "string" } }, required: ["day"] },
};
const ws = new WebSocket(`${process.env.PINECALL_URL.replace("http", "ws")}/v1/apps`, {
  headers: { authorization: `Bearer ${process.env.PINECALL_KEY}` },
});
const send = (type, data, call = null) =>
  ws.send(JSON.stringify({ type, agent: AGENT, call, id: String(Date.now()), data }));

// Your own code: here a fixed answer, in your app a query to your agenda.
const freeSlots = async (day) => [`${day} 10:15`, `${day} 12:30`];

// What the agent IS. Declared once, for every call this socket takes. A greeting declared here
// (`greeting: { say: "Clínica Norte, ¿en qué puedo ayudarle?" }`) is read, and wins over the
// settings' while this socket holds the agent; leave it out and the settings say how a call opens.
ws.on("open", () => {
  send("agent.register", { routes: [{ channel: "web", number: null }], sdk: "mine/0.1" });
  send("agent.configure", {
    config: {
      language: "es-ES",
      tools: [FREE_SLOTS],
    },
  });
});

ws.on("message", async (frame) => {
  const entry = JSON.parse(frame.toString());

  // A call opened on this agent: write the prompt and say which tools the model may see.
  if (entry.type === "call.started") {
    send("prompt.set", { name: "identity", text: "Eres la recepción de Clínica Norte. Hablas de usted." }, entry.call);
    send("tools.set", { tools: [FREE_SLOTS] }, entry.call);   // whole specs, so a tool may change
  }

  // The model asked for a tool. It runs HERE, in your process, against your database.
  if (entry.type === "tool.call") {
    const output = await freeSlots(entry.data.arguments.day);
    send("tool.result", { call_id: entry.data.call_id, name: entry.data.name, output }, entry.call);
  }
});
```

That is a complete Pinecall app: forty-odd lines, one dependency, no Pinecall package. Everything
`pinecall` adds (the class, the tools, the prompt, the goldens) is sugar over these frames. The
call it answers goes: `agent.registered` · `agent.configured` · `call.started` · `prompt.changed` ·
`tools.changed` · `turn.user` · `tool.call` · `tool.result` · `turn.agent`.
