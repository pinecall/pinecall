// Brightside Dental's voice app: its line, who answers it, who the call may pass to, and what its agents share.

import { flow, voiceApp } from "@pinecall/agents";

import Billing from "./agents/brightside-billing/agent.js";
import FrontDesk from "./agents/brightside-front-desk/agent.js";
import Reminder from "./agents/brightside-reminder/agent.js";
import { clinic, startsAt, ZONE, type Visit } from "./lib/clinic.js";

const app = voiceApp("brightside-dental", { timezone: ZONE });

app.line("+1 415 555 0134", {
  greeting: "Brightside Dental. How can I help?",
  answers: FrontDesk,
  team: [Billing],
});

app.rule("Never say an amount of money that a tool did not give you.");
app.silence({ after: "8s", say: "Are you still there?", times: 2 });

// A flow outlives the call that started it: the gateway keeps where it stands, and wakes it. The day
// before the visit the reminder calls the patient, and once more two hours later when nobody answered.
export const remindVisit = flow("remind-visit", async (booked, step) => {
  const visit = booked as unknown as Visit & { phone: string };
  // A visit booked in writing has no number to call.
  if (!visit.phone.startsWith("+")) return;
  await step.sleepUntil(startsAt(visit), { before: "24h" });
  const reminder = {
    state: { visit: visit.id },
    instruction: `Remind ${visit.patient} of the visit with ${visit.with} on ${visit.day} at ${visit.time}, and ask whether they are still coming.`,
  };
  let called = await step.call(visit.phone, Reminder, reminder);
  if (!called.answered && called.refused === undefined) {
    await step.sleep("2h");
    called = await step.call(visit.phone, Reminder, reminder);
  }
  await step.run(() => void clinic.reminded.push({ visit: visit.id, answered: called.answered }));
}).cancelOn("visit.cancelled", (gone, visit) => gone["id"] === visit["id"]);

// What an agent logs by name, and what happens to a call, reach the app.
app.on("visit.booked", remindVisit);

app.on("call.ended", (call, ended) => {
  clinic.callsKept.push({ call: call.id ?? "", agent: call.agent, reason: String(ended["reason"] ?? "") });
});

export default app;
