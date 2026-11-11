// What Brightside's agents put on a caller's page: each part is a name the page maps to a component of its own (ui/).

import { part, type Asked } from "@pinecall/agents";

import type { Invoice, Slot, Visit } from "./clinic.js";

/** Whose desk the caller is at: the page takes its colours from it. */
export const Stage = part<{ desk: "front" | "billing" }>("stage");

/** Nothing asked yet: who the caller is, when the clinic knows. */
export const Welcome = part<{ patient?: string | undefined }>("welcome");

/** The open times last read from the agenda; the caller may tap one. */
export const Agenda = part<{ slots: Slot[]; picked?: string | undefined }>("agenda");

/** What a tool stopped to ask for, as a form the caller may fill in the model's place. */
export const Form = part<Asked>("form");

/** A booked visit, and when its reminder calls. */
export const Ticket = part<{ visit: Visit; phone: string; remindedAt: string }>("ticket");

/** The caller's invoices; the one a refund was asked for, and the one the call was passed with. */
export const Invoices = part<{ invoices: Invoice[]; about?: string | undefined; refundAsked?: string | undefined }>("invoices");
