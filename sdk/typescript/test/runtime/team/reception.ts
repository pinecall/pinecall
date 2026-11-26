// Fixture: an agent that answers with state of its own, which its onCall sets and the state a call opened in replaces.

import { Agent, agent, tool, type Call } from "../../../src/index.js";

/** You are the reception. */
@agent({ takes: "anything about a visit" })
export default class Reception extends Agent {
  patient = "";
  visits: string[] = [];

  override onCall(_call: Call) {
    this.patient = "nobody yet";
    this.visits = [];
  }

  /** How many visits the caller has on the books. */
  @tool()
  onTheBooks() {
    return this.visits.length;
  }
}
