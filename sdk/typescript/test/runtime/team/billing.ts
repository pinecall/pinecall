// Fixture: the teammate a call is passed to; it reads what it was handed and what the call's agents share.

import { Agent, tool, type Call } from "../../../src/index.js";

/** You handle charges, invoices and refunds. */
export default class Billing extends Agent {
  static takes = "a question about a charge, an invoice or a refund";
  invoice = "";

  override onCall(_call: Call) {
    this.invoice = String(this.call.handed?.["invoice"] ?? "");
    this.call.shared["seenBy"] = "billing";
  }

  /** What the caller owes. */
  @tool()
  balance() {
    return 42;
  }
}
