// The front desk of Brightside Dental: it answers the clinic's line, books visits, and passes a charge to billing.

import { Agent, GetPhone, agent, tool, type Call } from "@pinecall/agents";

import { clinic, startsAt, type Patient, type Slot, type Visit } from "../../lib/clinic.js";
import { Agenda, Form, Stage, Ticket, Welcome } from "../../lib/screen.js";
import Billing from "../brightside-billing/agent.js";
import { hurried, offersARealTime } from "./harness.js";

/**
 * You are the front desk of Brightside Dental. You book, move and explain visits.
 * Short sentences. Offer at most two times. Never say a time the agenda did not give you.
 * Read the day and the time back and wait for a yes before you book.
 */
@agent({
  stt: "deepgram/flux-general-en",
  llm: "google/gemini-3.5-flash-lite",
  voice: "cartesia/f786b574-daa5-4673-aa0c-cbe3e8534c02",
  takes: "booking, moving or asking about a visit",
  judges: ["grounded", "promises", offersARealTime],
  personas: [hurried],
  tasks: [GetPhone],
  // What the caller's screen can show. A tool that shows one puts it up; a turn about something else takes it away.
  scenes: { agenda: "the open times you last read", ticket: "the visit booked on this call" },
  // What the caller's page may tell this agent: the time they tapped on its agenda, and the number they are known by.
  events: { "slot.picked": { from: ["participant"] }, "caller.known": { from: ["participant"] } },
})
export default class FrontDesk extends Agent {
  /** The times last read from the agenda: the only ones the agent may offer. */
  slots: Slot[] = [];
  /** The time the caller tapped on their page, as `day time`. */
  picked = "";
  /** The number the caller's page said they are known by, when the call itself brought none. */
  known = "";
  /** The visit this call booked, with the number its reminder calls. */
  visit: (Visit & { phone: string }) | null = null;

  // The patient is looked up once, as the call arrives, and shared with whoever takes the call next. `contact`
  // is who is calling: the number on a phone call, and who a written call says it is (`pinecall chat --as`).
  override onCall(call: Call) {
    const patient = clinic.patientByPhone(call.contact);
    if (patient !== undefined) this.call.shared["patient"] = patient;
  }

  /** The open times of one day. `day` is YYYY-MM-DD, counted from today. */
  @tool({ announce: "Let me check the agenda.", shows: "agenda" })
  freeSlots(day: string) {
    this.slots = clinic.free(day);
    this.picked = "";
    this.visit = null;
    if (this.slots.length === 0) return `Nothing is open on ${day}. Offer the next weekday.`;
    return this.slots;
  }

  /** Book one of the times freeSlots returned, once the caller said yes to it. */
  @tool({ shows: "ticket" })
  async book(day: string, time: string, name: string) {
    if (!this.slots.some((slot) => slot.day === day && slot.time === time)) return "That time did not come from the agenda. Call freeSlots for that day first.";
    // The reminder calls the number the patient called from. One who wrote has none: the tool stops to ask for it.
    const phone = this.call.contact.startsWith("+") ? this.call.contact : this.known !== "" ? this.known : await this.ask(GetPhone);
    const visit = clinic.book(day, time, name);
    if (visit === undefined) return "That time was just taken. Call freeSlots again and offer another.";
    // A line on the call's log, which the app hears by its name: it starts the visit's reminder (app.ts).
    this.log("visit.booked", { ...visit, phone });
    this.visit = { ...visit, phone };
    return visit;
  }

  // A tap on the page's agenda is not a yes: the model reads the time back and books on the caller's word.
  override onEvent(name: string, tapped: Record<string, unknown>) {
    if (name === "caller.known") return this.knows(String(tapped["phone"] ?? ""));
    const slot = this.slots.find((open) => open.day === tapped["day"] && open.time === tapped["time"]);
    if (slot === undefined) return;
    this.picked = `${slot.day} ${slot.time}`;
    void this.reply(`The caller tapped ${slot.day} at ${slot.time} with ${slot.with} on their screen. Read it back and ask for their yes; book it once they say it.`);
  }

  // A page has no caller id: it says which patient its visitor is, and the clinic looks the number up as it does a call's.
  private knows(phone: string): void {
    const patient = clinic.patientByPhone(phone);
    if (patient === undefined) return;
    this.known = patient.phone;
    this.call.shared["patient"] = patient;
  }

  // What the caller's page shows: the form of what a tool asks for, else the scene up now (the agenda, the
  // ticket), else the welcome. The page draws each part its own way (ui/).
  override screen() {
    const asked = this.call.asking;
    const patient = this.call.shared["patient"] as Patient | undefined;
    const scene = this.call.scene;
    return (
      <Stage desk="front">
        {asked !== undefined ? (
          <Form {...asked} />
        ) : scene === "ticket" && this.visit !== null ? (
          <Ticket visit={this.visit} phone={this.visit.phone} remindedAt={new Date(startsAt(this.visit).getTime() - 24 * 3_600_000).toISOString()} />
        ) : scene === "agenda" && this.slots.length > 0 ? (
          <Agenda slots={this.slots} picked={this.picked} />
        ) : (
          <Welcome patient={patient?.name} />
        )}
      </Stage>
    );
  }

  /** The caller disputes one charge and you know which invoice: pass the call to billing with it. */
  @tool()
  disputeCharge(invoice: string) {
    return this.call.handoff(Billing, { invoice });
  }
}
