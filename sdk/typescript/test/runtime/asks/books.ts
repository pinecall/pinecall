// Fixture: an agent whose booking tool asks the caller for an email before it finishes.

import { Agent, GetEmail, tool } from "../../../src/index.js";

/** You book visits. */
export default class Books extends Agent {
  static tasks = [GetEmail];

  /** Where the last confirmation was sent. */
  sentTo = "";

  /** Book a time, once the caller said yes to it. */
  @tool()
  async book(time: string) {
    this.sentTo = await this.ask(GetEmail);
    return { time, confirmation: this.sentTo };
  }

  /** The clinic's opening hours. */
  @tool()
  hours() {
    return "9 to 6";
  }
}
