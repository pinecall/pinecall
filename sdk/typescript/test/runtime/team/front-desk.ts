// Fixture: the agent that answers a team's line, and passes a disputed charge on with its invoice.

import { Agent, tool } from "../../../src/index.js";

import Billing from "./billing.js";

/** You are the front desk. */
export default class FrontDesk extends Agent {
  static takes = "anything about a visit";

  /** The caller disputes a charge and names the invoice. */
  @tool()
  disputeCharge(invoice: string) {
    return this.call.handoff(Billing, { invoice });
  }
}
