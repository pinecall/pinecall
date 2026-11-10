/** Numbers in the page's words: what a call to one does, where it comes through, and the ways to add one. */

import { prettyNumber } from "@pinecall/core/calls";
import type { IconName } from "../shell/icons";
import type { Carrier, Catalog, NumberRow, Rings } from "./door";

export const RINGS: Record<Rings, { mood: "good" | "warn" | "bad"; said: string }> = {
  ok: { mood: "good", said: "Rings the agent" },
  waiting: { mood: "warn", said: "Not reaching us yet" },
  broken: { mood: "bad", said: "Not answered" },
};

/** A number as a person reads it; a WhatsApp or odd one as it is. */
export function shown(number: string | null): string {
  return number === null ? "No number" : prettyNumber(number);
}

/** A number as it is typed, made E.164: spaces, dashes and brackets out. */
export function e164(typed: string): string {
  return typed.replace(/[\s().-]/g, "");
}

const KINDS: Record<Carrier["kind"], string> = { twilio: "Twilio", sip: "Your PBX", whatsapp: "WhatsApp" };

/** A carrier account in a line: what it is, and the name it was given. */
export function accountName(carrier: Carrier): string {
  return carrier.label === "" ? `${KINDS[carrier.kind]} ${carrier.account.slice(0, 8)}…` : `${carrier.label} (${KINDS[carrier.kind]})`;
}

/** Where a number comes through, in a few words. */
export function comesThrough(row: NumberRow, carriers: readonly Carrier[], catalog: Catalog | null): string {
  if (row.route.managed || row.origin === "bought") return "Bought from Pinecall";
  const account = carriers.find((one) => one.account === row.account);
  if (account !== undefined) return accountName(account);
  if (row.via != null) return `${catalog?.carriers.find((one) => one.kind === row.via)?.name ?? row.via}, pointed here by you`;
  if (row.origin === "typed") return "Added by the operator";
  return row.origin === "hooked" ? "Your carrier, pointed here by you" : "An account since removed";
}

/** A way to add a number: what it is called, what it takes, and its form. */
export interface Way {
  id: "buy" | "twilio" | "guided" | "pbx" | "whatsapp";
  name: string;
  says: string;
  icon: IconName;
  /** The catalog carrier a guided way points numbers through. */
  via?: string;
}

/** The ways this deployment offers for a channel, quickest first: buying where it sells, each carrier it admits, an own PBX, WhatsApp. */
export function waysOffered(catalog: Catalog, channel: "phone" | "whatsapp" | null): Way[] {
  const phone: Way[] = [
    ...(catalog.sells ? [{ id: "buy" as const, name: "Buy a number", says: "Pick a country and it rings in seconds, on Pinecall's account.", icon: "coins" as const }] : []),
    ...catalog.carriers.map((carrier): Way => (carrier.how === "automatic" ? { id: "twilio", name: `Bring one from ${carrier.name}`, says: "Connect your account once. We list its numbers and point the one you pick here.", icon: "numbers" } : { id: "guided", name: `Point one from ${carrier.name}`, says: `Paste one address in ${carrier.name}'s portal. Its calls are already trusted here.`, icon: "route", via: carrier.kind })),
    { id: "pbx", name: "Your own PBX or carrier", says: "Asterisk, FreePBX, 3CX, a local carrier. Its addresses are approved once.", icon: "server" },
  ];
  const whatsapp: Way = { id: "whatsapp", name: "WhatsApp", says: "A WhatsApp Business number. Messages reach the agent and it replies from it.", icon: "chat" };
  return channel === "whatsapp" ? [whatsapp] : channel === "phone" ? phone : [...phone, whatsapp];
}
