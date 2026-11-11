// Brightside Dental's own systems, as the agents reach them: the agenda, the patients and the ledger. A
// stand-in kept in memory, with the shapes a real clinic's API would answer.

export interface Patient {
  id: string;
  name: string;
  phone: string;
}

export interface Slot {
  /** `YYYY-MM-DD`. */
  day: string;
  /** `HH:MM`, on the clinic's clock. */
  time: string;
  with: string;
}

export interface Visit extends Slot {
  id: string;
  patient: string;
}

export interface Invoice {
  id: string;
  patient: string;
  what: string;
  amount: number;
  paid: boolean;
}

const PATIENTS: Patient[] = [
  { id: "p-1", name: "Ana Lopez", phone: "+14155550142" },
  { id: "p-2", name: "Jordan Lee", phone: "+14155550187" },
];

const INVOICES: Invoice[] = [
  { id: "inv-301", patient: "p-1", what: "cleaning", amount: 120, paid: true },
  { id: "inv-302", patient: "p-1", what: "cleaning", amount: 120, paid: true },
  { id: "inv-417", patient: "p-2", what: "filling", amount: 240, paid: false },
];

const HOURS = ["09:30", "11:00", "15:30"];
const DENTISTS = ["Dr. Lin", "Dr. Okafor"];

/** The clinic opens Monday to Friday, 9:00 to 18:00, on its own clock. */
export const OPENS = 9;
export const CLOSES = 18;

export class Clinic {
  readonly visits: Visit[] = [];
  readonly refundsAsked: { invoice: string; reason: string }[] = [];
  /** The visits whose reminder is owed, and every call that ended: what the app writes down. */
  readonly reminders: string[] = [];
  readonly callsKept: { call: string; agent: string; reason: string }[] = [];

  /** The patient a phone number belongs to. */
  patientByPhone(phone: string): Patient | undefined {
    const digits = phone.replace(/\D/g, "");
    return PATIENTS.find((patient) => patient.phone.replace(/\D/g, "") === digits);
  }

  /** The open times of a day: none on a weekend, and never one already booked. */
  free(day: string): Slot[] {
    const weekday = new Date(`${day}T12:00:00Z`).getUTCDay();
    if (Number.isNaN(weekday) || weekday === 0 || weekday === 6) return [];
    return HOURS.map((time, at) => ({ day, time, with: DENTISTS[at % DENTISTS.length]! })).filter(
      (slot) => !this.visits.some((visit) => visit.day === slot.day && visit.time === slot.time),
    );
  }

  /** Book a time that is still open; undefined when it was taken meanwhile. */
  book(day: string, time: string, patient: string): Visit | undefined {
    const slot = this.free(day).find((open) => open.time === time);
    if (slot === undefined) return undefined;
    const visit: Visit = { ...slot, id: `v-${this.visits.length + 1}`, patient };
    this.visits.push(visit);
    return visit;
  }

  /** A patient's invoices, the newest last. */
  invoicesOf(patient: string): Invoice[] {
    return INVOICES.filter((invoice) => invoice.patient === patient);
  }

  invoice(id: string): Invoice | undefined {
    return INVOICES.find((invoice) => invoice.id === id);
  }

  /** A refund is asked for, never given: a person at the office decides it. */
  askRefund(invoice: string, reason: string): void {
    this.refundsAsked.push({ invoice, reason });
  }
}

/** The one clinic the agents of this project share. */
export const clinic = new Clinic();
