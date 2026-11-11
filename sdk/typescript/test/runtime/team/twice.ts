// Fixture: an agent whose tool has the name of a teammate's.

import { Agent, tool } from "../../../src/index.js";

/** You answer about balances too. */
export default class Twice extends Agent {
  /** What the caller owes, by another count. */
  @tool()
  balance() {
    return 0;
  }
}
