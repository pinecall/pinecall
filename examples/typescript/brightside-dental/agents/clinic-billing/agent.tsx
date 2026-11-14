import { Agent, agent, tool } from "@pinecall/agents";

import { clinic, type Invoice, type Patient } from "../../lib/clinic.js";

/**
 * You are the billing desk of Brightside Dental. You explain charges and take refund requests.
 * Say amounts in dollars. You never promise a refund: a person at the office decides it.
 * An invoice says its number, its amount and whether it is paid; never say what a charge was for.
 */
@agent({
  voice: "cartesia/a5136bf9-224c-4d76-b823-52bd5efcffcc", // Jameson
  takes: "a question about a charge, an invoice, a payment or a refund",
})
export default class Billing extends Agent {
  /** The invoices of the patient on the call. */
  invoices: Invoice[] = [];

  // The front desk already found the patient: what the call's agents share comes with the call.
  override onCall() {
    const patient = this.call.shared["patient"] as Patient | undefined;
    if (patient !== undefined) this.invoices = clinic.invoicesOf(patient);
  }

  /** Take a refund request for one invoice. The office decides it and calls back. */
  @tool({ announce: "Let me write that down." })
  askRefund(invoice: string, reason: string) {
    clinic.askRefund(invoice, reason);
    return "Written down. Say the office will call back within one business day, and promise nothing else.";
  }

  override render() {
    return <p>Their invoices: {this.invoices.map((one) => `${one.id}, $${one.amount}, ${one.paid ? "paid" : "unpaid"}`).join("; ") || "none on file"}.</p>;
  }
}
