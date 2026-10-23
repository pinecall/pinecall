// Fixture agent loaded through tsx by the serve entry: a tool with a private argument and a private field.

import { Agent, state, tool } from "../../../../../src/index.js";

/** Atiende el mostrador. */
export default class Desk extends Agent {
  @state({ pii: true }) patient?: string;
  @state message?: { name: string };

  /** Writes down who called. */
  @tool({ pii: ["name"] })
  takeMessage(name: string): string {
    this.message = { name };
    return name;
  }
}
