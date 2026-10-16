/** An agent's calls read as conversations: one thread per person, newest first, and what its row says. */

import { type SessionLine } from "@pinecall/core/wire/rest";

import { prettyNumber, wantsAPerson } from "@pinecall/core/calls";
import { duration, lettersFor, visitorOf } from "../../lib/format";

/** One person's calls with this agent, newest first. */
export interface Thread {
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

/** The calls grouped by who was on them, the thread with the newest call first. */
export function threadsOf(lines: readonly SessionLine[]): Thread[] {
  const found = new Map<string, Thread>();
  for (const line of lines) {
    const contact = line.caller?.id ?? line.caller?.phone ?? addressOf(line) ?? line.call;
    const standing = found.get(contact);
    if (standing === undefined) {
      found.set(contact, { contact, name: line.caller?.name ?? null, handle: handleOf(line), lines: [line], latest: line });
      continue;
    }
    standing.lines.push(line);
    standing.name ??= line.caller?.name ?? null;
    if ((line.started_at ?? 0) > (standing.latest.started_at ?? 0)) standing.latest = line;
  }
  const threads = [...found.values()];
  for (const thread of threads) thread.lines.sort((a, b) => (b.started_at ?? 0) - (a.started_at ?? 0));
  // Newest first, except that a contact waiting for a person comes before every other: that is
  // the one row in this list somebody has to answer.
  return threads.sort(
    (a, b) => Number(wantsAPerson(b.latest)) - Number(wantsAPerson(a.latest)) || (b.latest.started_at ?? 0) - (a.latest.started_at ?? 0),
  );
}

function handleOf(line: SessionLine): string {
  const address = addressOf(line);
  if (address === null) return line.channel === "web" ? "web visitor" : "—";
  if (address.startsWith("+")) return prettyNumber(address);
  return line.channel === "web" ? "web visitor" : address;
}

/** What a thread is called: its name, its number, or the web visitor as the Calls list names them. */
export function titleOf(thread: Thread): string {
  if (thread.name !== null && thread.name !== "") return thread.name;
  if (thread.contact.startsWith("+")) return prettyNumber(thread.contact);
  return visitorOf(thread.contact) ?? thread.contact;
}

/** Two letters for a person, one for a web visitor, a number's last two digits for a number nobody named. */
export function lettersOf(thread: Thread): string | undefined {
  return lettersFor(thread.name, thread.handle === "web visitor" ? "web" : thread.contact);
}

/** What a thread's row says under its name: the newest call's outcome, or how it went. */
export function lastOf(thread: Thread): string {
  const line = thread.latest;
  if (line.status !== "ended") return "On a call now";
  if (line.outcome !== null && line.outcome !== "") return line.outcome;
  return `${line.channel ?? "a"} call · ${duration(line)}`;
}
