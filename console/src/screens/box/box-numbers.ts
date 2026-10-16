/** A number of the box read for its Routes row: how it came, what a call to it does now, and whether a search finds it. */

import type { Tone } from "../../ui";
import { type BoxNumber } from "./door-floor";

// Runtime docs/protocol/operator-api.md, "Routes": a value the runtime adds later reads as itself.
const CAME_IN: Record<string, string> = {
  bought: "bought by the box",
  twilio: "its Twilio",
  sip: "its SIP peer",
  whatsapp: "its WhatsApp",
  imported: "an account since removed",
  hooked: "hooked by the org",
  typed: "typed by an operator",
};

/** How the number reached the box, in the screen's words. */
export function cameIn(row: BoxNumber): string {
  return CAME_IN[row.came_in] ?? row.came_in;
}

/** What a call to the number does now: none opens until the operator approves it, nobody runs the agent, or it is picked up. */
export function whenItRings(row: BoxNumber): { tone: Tone; text: string } {
  if (!row.approved) return { tone: "red", text: "waits for your approval" };
  if (!row.running) return { tone: "amber", text: "nobody runs the agent" };
  return { tone: "green", text: "picked up" };
}

/** The rows whose number, org or agent holds the words; a number is matched by its digits alone. */
export function matching(rows: readonly BoxNumber[], words: string): BoxNumber[] {
  const wanted = words.trim().toLowerCase();
  if (wanted === "") return [...rows];
  const digits = wanted.replace(/\D/g, "");
  return rows.filter(
    (row) => row.org.toLowerCase().includes(wanted) || row.agent.toLowerCase().includes(wanted) || (digits !== "" && row.number.replace(/\D/g, "").includes(digits)),
  );
}
