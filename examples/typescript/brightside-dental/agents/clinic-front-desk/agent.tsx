import { Agent, agent, tool, type Call } from "@pinecall/agents";

import { clinic, type Slot } from "../../lib/clinic.js";
import { offersARealTime } from "./judges.js";
import { chargedTwice, hurried } from "./personas.js";

/**
 * You are the front desk of Brightside Dental. You book, move and explain visits.
 * Short sentences. Offer at most two times. Never say a time the agenda did not give you.
 * Before you book a time, ask the caller's name. Never book without it.
 */
@agent({
  stt: "deepgram/flux-general-en",
  llm: "google/gemini-3.5-flash-lite",
  voice: "cartesia/f786b574-daa5-4673-aa0c-cbe3e8534c02", // Katie
  takes: "booking, moving or asking about a visit",
  judges: ["consent", "grounded", offersARealTime],
  personas: [hurried, chargedTwice],
})
export default class FrontDesk extends Agent {
  /** The times last read from the agenda: the only ones the agent may offer. */
  slots: Slot[] = [];

  // The patient is found once, as the call arrives, and shared with whoever takes the call next.
  override onCall(call: Call) {
    this.call.shared["patient"] = clinic.patientByPhone(call.contact);
  }

  /** The open times of one day. `day` is YYYY-MM-DD. */
  @tool({ announce: "Let me check the agenda." })
  freeSlots(day: string) {
    this.slots = clinic.free(day);
    if (this.slots.length === 0) return "Nothing is open that day. Say just that, and ask about another day.";
    return this.slots;
  }

  /** Book one of the times freeSlots returned, once the caller chose it and gave their name. */
  @tool()
  book(day: string, time: string, name: string) {
    const offered = this.slots.some((slot) => slot.day === day && slot.time === time);
    if (!offered) return "That time did not come from the agenda. Call freeSlots for that day first.";
    const visit = clinic.book(day, time, name);
    // A line on the call's log, by its name: the app hears it and starts the visit's reminder (app.ts).
    this.log("visit.booked", { ...visit, phone: this.call.contact });
    return visit;
  }

  // What the model reads this turn, from the state: the times on the table, and nothing else to offer.
  override render() {
    if (this.slots.length === 0) return <p>No times are on the table yet.</p>;
    return <p>Offer only these times: {this.slots.map((slot) => slot.time).join(", ")}.</p>;
  }
}
