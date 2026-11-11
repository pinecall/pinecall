// The reminder of Brightside Dental: it calls a patient the day before a visit, for the flow that asked (app.ts).

import { Agent, tool } from "@pinecall/agents";

import { clinic } from "../../lib/clinic.js";

/**
 * You are calling a patient for Brightside Dental about a visit they booked. Say who is calling and why
 * in one sentence, then ask whether they are still coming. Two or three sentences in the whole call.
 * You do not book or move a visit: a patient who wants another time is told to call the clinic's line.
 */
export default class Reminder extends Agent {
  /** The visit this call is about: the state its flow opened the call in. */
  visit = "";

  /** The patient said they are coming. */
  @tool()
  confirmVisit() {
    clinic.confirm(this.visit);
    return "Written down. Thank them and say goodbye.";
  }

  /** The patient said they are not coming: the time is given back to the agenda. */
  @tool()
  cancelVisit() {
    clinic.cancel(this.visit);
    // The app hears it by its name, and a reminder still waiting for this visit is cancelled (app.ts).
    this.log("visit.cancelled", { id: this.visit });
    return "Cancelled. Tell them they can call the clinic's line to book another time, and say goodbye.";
  }
}
