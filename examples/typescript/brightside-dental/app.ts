// Brightside Dental's voice app: its line, who answers it, who the call may pass to, and what its agents share.

import { voiceApp } from "@pinecall/agents";

import Billing from "./agents/brightside-billing/agent.js";
import FrontDesk from "./agents/brightside-front-desk/agent.js";
import { clinic } from "./lib/clinic.js";

const app = voiceApp("brightside-dental", { timezone: "America/Los_Angeles" });

app.line("+1 415 555 0134", {
  greeting: "Brightside Dental. How can I help?",
  answers: FrontDesk,
  team: [Billing],
});

app.rule("Never say an amount of money that a tool did not give you.");
app.silence({ after: "8s", say: "Are you still there?", times: 2 });

// What an agent logs by name, and what happens to a call, reach the app.
app.on("visit.booked", (_call, visit) => {
  clinic.reminders.push(String(visit["id"]));
});

app.on("call.ended", (call, ended) => {
  clinic.callsKept.push({ call: call.id ?? "", agent: call.agent, reason: String(ended["reason"] ?? "") });
});

export default app;
