/** The calls read as conversations: one thread per person, who is waiting first, and what its row says. */

import { byDay, isARun, isLive, isSimulated, prettyNumber, wantsAPerson, type CallDay } from "@pinecall/core/calls";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { lengthOf, utcDay } from "../lib/format";
import { dayOf, goldenOf, lettersFor, simulationOf, visitorOf } from "./format";
import { goingSaid, kindNamed } from "./kind";

const A_SIMULATED_CALL = "simulated caller";
// A golden opens its call as a visitor of a page would, from an address of its own: read by its
// address, a run of four goldens was four web visitors nobody could place.
const A_GOLDEN_RUN = "golden run";

/** One person's calls, newest first. */
export interface Thread {
  /** What tells this row from the others: the contact when a row is a person, the call when it is one call. */
  key: string;
  /** Who the thread is with, as the log names them: the contact's id, their phone, or the web visitor's id. */
  contact: string;
  /** The contact's name when the platform recognised the caller. */
  name: string | null;
  /** How they reached the agent, said for a person: a number, or "web visitor". */
  handle: string;
  lines: SessionLine[];
  latest: SessionLine;
}

// The address a call came from — or went to, when the agent dialled — is who the thread is with.
function addressOf(line: SessionLine): string | null {
  return line.direction === "outbound" ? line.to : line.from;
}

// Every simulation comes from the one simulated caller: grouped by address, six run this morning
// would be one thread showing the last. Each is a conversation of its own, keyed by its call.
function contactOf(line: SessionLine): string {
  if (isARun(line) || isSimulated(line)) return line.call;
  return line.caller?.id ?? line.caller?.phone ?? addressOf(line) ?? line.call;
}

function handleOf(line: SessionLine): string {
  if (isARun(line)) return A_GOLDEN_RUN;
  if (isSimulated(line)) return A_SIMULATED_CALL;
  const address = addressOf(line);
  if (address === null) return line.channel === "web" ? "web visitor" : "—";
  if (address.startsWith("+")) return prettyNumber(address);
  // Meta names a Messenger or Instagram contact by an id of the Page's alone: said by where they wrote.
  if (line.channel === "messenger" || line.channel === "instagram") return line.channel === "messenger" ? "Messenger contact" : "Instagram contact";
  return line.channel === "web" ? "web visitor" : address;
}

/**
 * The calls as the list's rows: a person waiting for a human first, then whoever is on the line, then the newest.
 * Grouped, a row is a person and holds every call of theirs; one by one, each call is a row of its own.
 */
export function threadsOf(lines: readonly SessionLine[], grouped = true): Thread[] {
  const found = new Map<string, Thread>();
  for (const line of lines) {
    // Who the row is with is the same either way: ungrouped, only what tells the rows apart is the call.
    // A row keyed and NAMED by its call read "call-_+34607827824_…" where the caller's number goes.
    const contact = contactOf(line);
    // An email thread is a row of its own, as a mailbox lists it: one person writes on several subjects.
    const key = grouped && line.channel !== "email" ? contact : line.call;
    const standing = found.get(key);
    if (standing === undefined) {
      found.set(key, { key, contact, name: line.caller?.name ?? null, handle: handleOf(line), lines: [line], latest: line });
      continue;
    }
    standing.lines.push(line);
    standing.name ??= line.caller?.name ?? null;
    if ((line.started_at ?? 0) > (standing.latest.started_at ?? 0)) standing.latest = line;
  }
  const threads = [...found.values()];
  for (const thread of threads) thread.lines.sort((a, b) => (b.started_at ?? 0) - (a.started_at ?? 0));
  return threads.sort(
    (a, b) =>
      Number(wantsAPerson(b.latest)) - Number(wantsAPerson(a.latest)) ||
      Number(isLive(b.latest)) - Number(isLive(a.latest)) ||
      (b.latest.started_at ?? 0) - (a.latest.started_at ?? 0),
  );
}

/** The threads under "live" and then their newest call's day, in the order given. */
/** A day of the list: the days the calls are grouped under, and the written conversations still open, which are no day's. */
export type ThreadDay = CallDay<Thread> | { key: "open"; name: "open"; lines: Thread[] };

// What has not ended comes first, in two groups: the calls with somebody on the line, then the written
// conversations waiting for their contact, which stay open for hours and are never live.
export function threadDays(threads: readonly Thread[]): ThreadDay[] {
  const of = new Map(threads.map((thread) => [thread.latest.call, thread]));
  const days: ThreadDay[] = byDay(
    threads.map((thread) => thread.latest),
    utcDay,
  ).map((day) => ({ ...day, lines: day.lines.flatMap((line) => of.get(line.call) ?? []) }));
  return days.flatMap((day): ThreadDay[] => {
    if (day.name !== "live") return [day];
    const open = day.lines.filter((thread) => !isOnTheLine(thread.latest));
    const going = { ...day, lines: day.lines.filter((thread) => isOnTheLine(thread.latest)) };
    return [...(going.lines.length > 0 ? [going] : []), ...(open.length > 0 ? [{ key: "open" as const, name: "open" as const, lines: open }] : [])];
  });
}

/** What a thread is called: its name, its number, or the web visitor as the list names them. */
export function titleOf(thread: Thread): string {
  if (thread.name !== null && thread.name !== "") return thread.name;
  if (thread.handle === A_GOLDEN_RUN) return goldenOf(thread.contact);
  if (thread.handle === A_SIMULATED_CALL) return simulationOf(thread.contact);
  if (thread.contact.startsWith("+")) return prettyNumber(thread.contact);
  // A Messenger or Instagram contact Meta gave no name for: where they wrote, and the end of Meta's id of them.
  const meta = /^(messenger|instagram):(\d+)$/.exec(thread.contact);
  if (meta !== null) return `${meta[1] === "messenger" ? "Messenger" : "Instagram"} contact · ${meta[2]!.slice(-4)}`;
  return visitorOf(thread.contact) ?? thread.contact;
}

/** Two letters for a person, one for a web visitor or a simulation, a number's last two digits for a number nobody named. */
export function lettersOf(thread: Thread): string | undefined {
  if (thread.handle === A_GOLDEN_RUN) return "G";
  if (thread.handle === A_SIMULATED_CALL) return "S";
  return lettersFor(thread.name, thread.handle === "web visitor" ? "web" : thread.contact);
}

/** The channels a contact writes on message by message. */
const WRITTEN = new Set(["whatsapp", "sms", "email", "messenger", "instagram"]);

/** Whether a conversation is one a contact writes on a number: a WhatsApp or an SMS thread. */
export function isWritten(line: { channel: string | null }): boolean {
  return line.channel !== null && WRITTEN.has(line.channel);
}

/** Whether somebody is on the line now, as the gateway says it: a written conversation stays open for hours with nobody on it, and is never live. */
export function isOnTheLine(line: SessionLine): boolean {
  return line.live && isLive(line);
}

/** What a thread's row says under its name: the newest call's outcome, or how it went. */
export function lastOf(thread: Thread): string {
  const line = thread.latest;
  if (line.outcome !== null && line.outcome !== "") return line.outcome;
  if (line.status !== "ended") return thread.handle === A_GOLDEN_RUN ? "A golden, running now" : goingSaid(line);
  return `${kindNamed(line)}, ${lengthOf(line.started_at, line.ended_at)}`;
}

/** A group's title: who is on the line now (the conversations still open, of written ones), then Today, Yesterday and every day before by its date. */
export function dayName(day: { name: ThreadDay["name"]; at?: number }): string {
  switch (day.name) {
    case "live":
      return "On the line";
    case "open":
      return "Open, waiting for a reply";
    case "unstarted":
      return "Not started";
    case "today":
      return "Today";
    case "yesterday":
      return "Yesterday";
    case "before":
      return day.at === undefined ? "Before" : dayOf(day.at);
  }
}
