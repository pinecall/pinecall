// Brightside Dental's voice app: its line, who answers it, who the call may pass to, and what its agents share.

import { voiceApp } from "@pinecall/agents";

import Billing from "./agents/billing/agent.js";
import FrontDesk from "./agents/front-desk/agent.js";

const app = voiceApp("brightside-dental", { timezone: "America/Los_Angeles" });

app.line("+1 415 555 0134", {
  greeting: "Brightside Dental. How can I help?",
  answers: FrontDesk,
  team: [Billing],
});

app.silence({ after: "8s", say: "Are you still there?", times: 2 });

export default app;
