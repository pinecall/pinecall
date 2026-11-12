// Fixture: an agent whose screen follows the conversation: a tool puts the agenda up, and a turn about something else takes it away.

import { Agent, agent, part, tool } from "../../../src/index.js";

export const Times = part<{ times: string[] }>("times");
export const Hello = part("hello");

/** You book visits. */
@agent({ scenes: { agenda: "the open times you last read" } })
export default class Scenes extends Agent {
  times: string[] = [];

  /** The open times. */
  @tool({ shows: "agenda" })
  free() {
    this.times = ["09:30", "11:00"];
    return this.times;
  }

  override screen() {
    return this.call.scene === "agenda" ? Times({ times: this.times }) : Hello({});
  }
}
