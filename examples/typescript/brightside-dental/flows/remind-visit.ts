import { flow } from "@pinecall/agents";

import FrontDesk from "../agents/clinic-front-desk/agent.js";
import { startsAt, type Visit } from "../lib/clinic.js";

// Started by the app for every `visit.booked` an agent logs: app.on("visit.booked", remindVisit).
// A flow outlives the call that started it: Pinecall keeps where it stands, and wakes it. The day
// before the visit the agent calls the patient, and once more when nobody answered.
export const remindVisit = flow("remind-visit", async (booked, step) => {
  const visit = booked as unknown as Visit & { phone: string };
  // A visit booked from a web page left no number to ring: there is no reminder to place.
  if (!visit.phone.startsWith("+")) return;
  await step.sleepUntil(startsAt(visit), { before: "24h" });

  const reminder = {
    instruction: `Remind ${visit.patient} of the visit on ${visit.day} at ${visit.time}, and ask whether they are still coming.`,
  };
  let called = await step.call(visit.phone, FrontDesk, reminder);
  if (!called.answered) {
    await step.sleep("2h");
    called = await step.call(visit.phone, FrontDesk, reminder);
  }
}).cancelOn("visit.cancelled", (gone, visit) => gone["id"] === visit["id"]);
