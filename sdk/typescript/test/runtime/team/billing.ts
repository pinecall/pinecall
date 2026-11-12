// Fixture: the teammate a call is passed to; it reads what it was handed and what the call's agents share.

import { Agent, agent, tool, type Call } from "../../../src/index.js";

/** You handle charges, invoices and refunds. */
@agent({ takes: "a question about a charge, an invoice or a refund" })
export default class Billing extends Agent {
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
