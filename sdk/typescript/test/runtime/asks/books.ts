// Fixture: an agent whose booking tool asks the caller for an email before it finishes.

import { Agent, GetEmail, agent, tool } from "../../../src/index.js";

/** You book visits. */
@agent({ tasks: [GetEmail] })
export default class Books extends Agent {
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
