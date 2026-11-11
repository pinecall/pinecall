// The front desk of Brightside Dental: it answers the clinic's line, books visits, and passes a charge to billing.

import { Agent, judges, personas, tool, type Call } from "@pinecall/agents";

import { clinic, type Slot } from "../../lib/clinic.js";
import Billing from "../brightside-billing/agent.js";
import { hurried, offersARealTime } from "./harness.js";

/**
 * You are the front desk of Brightside Dental. You book, move and explain visits.
 * Short sentences. Offer at most two times. Never say a time the agenda did not give you.
 * Read the day and the time back and wait for a yes before you book.
 */
export default class FrontDesk extends Agent {
  static takes = "booking, moving or asking about a visit";
  static judges = judges({ on: ["grounded", "promises"], own: [offersARealTime] });
  static personas = personas({ own: [hurried] });

  /** The times last read from the agenda: the only ones the agent may offer. */
  slots: Slot[] = [];

  // The patient is looked up once, as the call arrives, and shared with whoever takes the call next. `contact`
  // is who is calling: the number on a phone call, and who a written call says it is (`pinecall chat --as`).
  override onCall(call: Call) {
    const patient = clinic.patientByPhone(call.contact);
    if (patient !== undefined) this.call.shared["patient"] = patient;
  }

  /** The open times of one day. `day` is YYYY-MM-DD, counted from today. */
  @tool({ announce: "Let me check the agenda." })
  freeSlots(day: string) {
    this.slots = clinic.free(day);
    if (this.slots.length === 0) return `Nothing is open on ${day}. Offer the next weekday.`;
    return this.slots;
  }

  /** Book one of the times freeSlots returned, once the caller said yes to it. */
  @tool()
  book(day: string, time: string, name: string) {
    if (!this.slots.some((slot) => slot.day === day && slot.time === time)) return "That time did not come from the agenda. Call freeSlots for that day first.";
    const visit = clinic.book(day, time, name);
    if (visit === undefined) return "That time was just taken. Call freeSlots again and offer another.";
    // A line on the call's log, which the app hears by its name (app.ts).
    this.log("visit.booked", visit);
    return visit;
  }

  /** The caller disputes one charge and you know which invoice: pass the call to billing with it. */
  @tool()
  disputeCharge(invoice: string) {
    return this.call.handoff(Billing, { invoice });
  }
}
