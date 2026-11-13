import { voiceApp } from "@pinecall/agents";

import Billing from "./agents/clinic-billing/agent.js";
import FrontDesk from "./agents/clinic-front-desk/agent.js";
import { remindVisit } from "./flows/remind-visit.js";

const app = voiceApp("brightside", { timezone: "America/Los_Angeles" });

// One number and a team behind it: the front desk answers, and the call may pass to billing.
app.line("+1 415 555 0134", {
  greeting: "Brightside Dental. How can I help?",
  answers: FrontDesk,
  team: [Billing],
});

// What every agent of the app is held to, and what it says when the caller goes quiet.
app.rule("Never say an amount of money that a tool did not give you.");
app.silence({ after: "8s", say: "Are you still there?", times: 2 });

// The front desk logs `visit.booked` when its `book` tool books a visit. The app hears it and
// starts that visit's reminder: a flow, which goes on after the call is over.
app.on("visit.booked", remindVisit);

export default app;
