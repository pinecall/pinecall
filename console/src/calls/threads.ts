/** The calls read as conversations: one thread per person, who is waiting first, and what its row says. */

import { byDay, isARun, isLive, isSimulated, prettyNumber, wantsAPerson, type CallDay } from "@pinecall/core/calls";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { lengthOf, utcDay } from "../lib/format";
import { dayOf, goldenOf, lettersFor, simulationOf, visitorOf } from "./format";

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
    const key = grouped ? contact : line.call;
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
export function threadDays(threads: readonly Thread[]): CallDay<Thread>[] {
  const of = new Map(threads.map((thread) => [thread.latest.call, thread]));
  return byDay(
    threads.map((thread) => thread.latest),
    utcDay,
  ).map((day) => ({ ...day, lines: day.lines.flatMap((line) => of.get(line.call) ?? []) }));
}

/** What a thread is called: its name, its number, or the web visitor as the list names them. */
export function titleOf(thread: Thread): string {
  if (thread.name !== null && thread.name !== "") return thread.name;
  if (thread.handle === A_GOLDEN_RUN) return goldenOf(thread.contact);
  if (thread.handle === A_SIMULATED_CALL) return simulationOf(thread.contact);
  if (thread.contact.startsWith("+")) return prettyNumber(thread.contact);
  return visitorOf(thread.contact) ?? thread.contact;
}

/** Two letters for a person, one for a web visitor or a simulation, a number's last two digits for a number nobody named. */
export function lettersOf(thread: Thread): string | undefined {
  if (thread.handle === A_GOLDEN_RUN) return "G";
  if (thread.handle === A_SIMULATED_CALL) return "S";
  return lettersFor(thread.name, thread.handle === "web visitor" ? "web" : thread.contact);
}

/** What a thread's row says under its name: the newest call's outcome, or how it went. */
export function lastOf(thread: Thread): string {
  const line = thread.latest;
  if (line.outcome !== null && line.outcome !== "") return line.outcome;
  if (line.status !== "ended") return thread.handle === A_GOLDEN_RUN ? "A golden, running now" : "On a call now";
  return `${line.channel ?? "A"} call, ${lengthOf(line.started_at, line.ended_at)}`;
}

/** A group's title: who is on the line now, then Today, Yesterday and every day before by its date. */
export function dayName(day: Pick<CallDay<unknown>, "name"> & { at?: number }): string {
  switch (day.name) {
    case "live":
      return "On the line";
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
