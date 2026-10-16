/** Numbers in the screen's words: what a call to one does, where it comes through, and the ways to add one. */

import type { Tone } from "../../ui";
import type { Answering, Carrier, Catalog, Rings } from "./door";

/** What a call to the number does now, as the list says it. */
export const RINGS_SAID: Record<Rings, { tone: Tone; text: string }> = {
  ok: { tone: "green", text: "Rings the agent" },
  waiting: { tone: "amber", text: "Not reaching us yet" },
  broken: { tone: "red", text: "Not answered" },
};

/** Who wrote the number's row: the pill beside it. A row the org did not write is how it learns the operator did. */
export const ORIGIN_SAID: Record<Answering["origin"], { tone: Tone; text: string }> = {
  imported: { tone: "gray", text: "your account" },
  hooked: { tone: "indigo", text: "pointed by you" },
  bought: { tone: "violet", text: "bought here" },
  typed: { tone: "amber", text: "added by the box operator" },
};

const KIND_NAMED: Record<Carrier["kind"], string> = { twilio: "Twilio", sip: "Your PBX", whatsapp: "WhatsApp" };

/** Where a number comes through, and a second line under it. */
export function comesThrough(row: Answering, carriers: Carrier[], catalog: Catalog | null): { name: string; sub: string } {
  if (row.route.managed) return { name: "Pinecall", sub: "bought for you" };
  const account = carriers.find((one) => one.account === row.account);
  if (account !== undefined) return { name: account.kind === "sip" && account.label !== "" ? account.label : KIND_NAMED[account.kind], sub: account.label !== "" && account.kind !== "sip" ? `${account.label} · ${account.account}` : account.account };
  if (row.via != null) return { name: catalog?.carriers.find((one) => one.kind === row.via)?.name ?? row.via, sub: "pointed here by you" };
  if (row.origin === "typed") return { name: "The box operator", sub: "no account" };
  if (row.origin === "imported") return { name: "An account since removed", sub: "it still rings" };
  return { name: "Your carrier", sub: "pointed here by you" };
}

/** A way into the org's numbers: what it is called, how much of it is the org's work, and a line of what happens. */
export interface Way {
  id: string;
  name: string;
  how: "automatic" | "guided" | "reviewed";
  says: string;
  /** The catalog carrier a guided way hooks numbers through. */
  via?: string;
}

/**
 * The ways offered, in the order the sheet draws them: buying when the box sells, the carriers its
 * operator admits (Twilio automatic, the rest guided), an own PBX (reviewed once by the operator),
 * and WhatsApp. A carrier the operator did not admit is not drawn at all.
 */
export function waysOffered(catalog: Catalog): Way[] {
  const ways: Way[] = [];
  if (catalog.sells) ways.push({ id: "buy", name: "Buy a number here", how: "automatic", says: "Pick a country. It works in seconds, bought on Pinecall's account." });
  for (const carrier of catalog.carriers) {
    ways.push(
      carrier.how === "automatic"
        ? { id: carrier.kind, name: carrier.name, how: "automatic", says: "Connect your account once. We list your numbers and point them here for you." }
        : { id: `via:${carrier.kind}`, name: carrier.name, how: "guided", says: `Paste one address in ${carrier.name}'s portal. This box already trusts ${carrier.name}.`, via: carrier.kind },
    );
  }
  ways.push({ id: "pbx", name: "Your own PBX or another carrier", how: "reviewed", says: "Asterisk, FreePBX, 3CX, a local carrier. The box operator approves your IP addresses once." });
  ways.push({ id: "whatsapp", name: "WhatsApp", how: "automatic", says: "A number on WhatsApp Business. Messages reach the agent, replies go out from it." });
  return ways;
}

/** How many of the numbers do each thing now: the line over the list. */
export function countRings(rows: Answering[]): Record<Rings, number> {
  const counted: Record<Rings, number> = { ok: 0, waiting: 0, broken: 0 };
  for (const row of rows) counted[row.rings] += 1;
  return counted;
}
