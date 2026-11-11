// The billing agent of Brightside Dental: it takes a call the front desk passes, already knowing the patient.

import { Agent, tool, type Call } from "@pinecall/agents";

import { clinic, type Invoice } from "../../lib/clinic.js";

/**
 * You are the billing desk of Brightside Dental. You explain charges and take refund requests.
 * Short sentences. Say amounts in dollars. You never promise a refund: a person at the office decides it.
 */
export default class Billing extends Agent {
  static takes = "a question about a charge, an invoice, a payment or a refund";

  /** The invoices of the patient on the call, found as the call arrives. */
  invoices: Invoice[] = [];

  override onCall(_call: Call) {
    const patient = this.call.shared["patient"] as { id: string } | undefined;
    if (patient !== undefined) this.invoices = clinic.invoicesOf(patient.id);
  }

  /** The patient's invoices: what each was for, its amount and whether it is paid. */
  @tool()
  listInvoices() {
    if (this.invoices.length === 0) return "No invoices on file for this caller. Ask for the phone number the visit was booked with.";
    return this.invoices;
  }

  /** Take a refund request for one invoice. The office decides it and calls back. */
  @tool({ announce: "Let me write that down." })
  askRefund(invoice: string, reason: string) {
    if (clinic.invoice(invoice) === undefined) return `There is no invoice ${invoice}. Read the ids back from listInvoices.`;
    clinic.askRefund(invoice, reason);
    return "Written down. Tell the caller the office will call back within one business day, and promise nothing else.";
  }
}
