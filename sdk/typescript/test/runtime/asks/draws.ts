// Fixture: an agent that draws a screen: the times it read, the form of what a tool asks for, the visit once booked.

import { Agent, GetEmail, part, tool } from "../../../src/index.js";

export const Times = part<{ times: string[]; picked: string }>("times");
export const Form = part<{ task: string; refused?: string }>("form");
export const Booked = part<{ time: string; sentTo: string }>("booked");
export const Banner = part<{ text: string }>("banner");

/** You book visits. */
export default class Draws extends Agent {
  static tasks = [GetEmail];
  static override events = { "time.picked": { from: ["participant" as const] } };

  times: string[] = [];
  picked = "";
  sentTo = "";

  /** The open times. */
  @tool()
  free() {
    this.times = ["09:30", "11:00"];
    return this.times;
  }

  /** Book a time, once the caller said yes to it. */
  @tool()
  async book(time: string) {
    this.sentTo = await this.ask(GetEmail);
    return { time, confirmation: this.sentTo };
  }

  /** Say something over the screen. */
  @tool()
  announce(text: string) {
    this.show(Banner({ text }));
    return "shown";
  }

  override onEvent(_name: string, data: Record<string, unknown>) {
    this.picked = String(data["time"]);
  }

  override screen() {
    const asked = this.call.asking;
    if (asked !== undefined) return Form({ task: asked.task, ...(asked.refused === undefined ? {} : { refused: asked.refused }) });
    if (this.sentTo !== "") return Booked({ time: this.picked, sentTo: this.sentTo });
    if (this.times.length > 0) return Times({ times: this.times, picked: this.picked });
    return null;
  }
}
