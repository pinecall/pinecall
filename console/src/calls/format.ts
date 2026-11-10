/** How a call is named and dated on this page: who was on it, when, how it stands, whose copy took it. */

import { NOTHING, isLive, prettyNumber, visitorId, wantsAPerson } from "@pinecall/core/calls";
import { type SessionLine } from "@pinecall/core/wire/rest";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** `15:10`, UTC, as every time on this page is. */
export function hourOf(at: number): string {
  return new Date(at * 1000).toISOString().slice(11, 16);
}

/** `16 Sep`, UTC. */
export function dayOf(at: number): string {
  const date = new Date(at * 1000);
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}`;
}

/** `16 Sep, 15:10`, UTC. */
export function dayAndTime(at: number | null): string {
  return at === null ? NOTHING : `${dayOf(at)}, ${hourOf(at)}`;
}

/** `$0.0142`: four decimals, as a call often costs less than a cent. */
export function usd(value: number | null | undefined): string {
  return value === null || value === undefined ? NOTHING : `$${value.toFixed(4)}`;
}

/** The calls waiting for a person first, then the other live ones, then the ended ones. */
export function liveFirst(lines: readonly SessionLine[]): SessionLine[] {
  const live = lines.filter(isLive);
  return [...live.filter(wantsAPerson), ...live.filter((line) => !wantsAPerson(line)), ...lines.filter((line) => !isLive(line))];
}

/** "Web visitor · 3f7d". */
export function webVisitor(id: string): string {
  return `Web visitor · ${id}`;
}

/** "Simulation · 3f7d": a simulated call named by its call id, as a web visitor is. */
export function simulationOf(call: string): string {
  return `Simulation · ${visitorId(call) ?? call}`;
}

/** A web visitor's name from their address, or null for any other address. */
export function visitorOf(address: string | null | undefined): string | null {
  const id = visitorId(address);
  return id === null ? null : webVisitor(id);
}

/** A number written for reading; any other address as it is. */
export function prettyOrAsIs(address: string): string {
  return address.startsWith("+") ? prettyNumber(address) : address;
}

/** Face letters when nobody named them: "W" for a web visitor, the last two digits of a number. */
export function lettersFor(name: string | null | undefined, address: string | null | undefined): string | undefined {
  if (name !== null && name !== undefined && name !== "") return undefined;
  if (address === null || address === undefined) return undefined;
  if (address.startsWith("+")) return address.slice(-2);
  return address.startsWith("web") || address.startsWith("call") ? "W" : undefined;
}

/** "Dana's copy" for a call a colleague's copy took; nothing for the reader's own or the org's. */
export function copyOf(line: SessionLine, me: string | null): string | undefined {
  if (line.holder === undefined || line.holder === null || line.holder === "" || line.holder === me) return undefined;
  return `${line.holder_name ?? "A colleague"}'s copy`;
}

/** The dash-mood a thing is said in. */
export type Mood = "calm" | "good" | "warn" | "bad";

export interface Standing {
  text: string;
  mood: Mood;
}

// The caller's own hang-up is the quiet one, a hand-off is worth a glance, and anything the platform did is red.
const ENDINGS: Record<string, Standing> = {
  caller_hung_up: { text: "Caller hung up", mood: "calm" },
  agent_hung_up: { text: "Agent hung up", mood: "calm" },
  supervisor_ended: { text: "Supervisor ended", mood: "calm" },
  transferred: { text: "Transferred", mood: "warn" },
  no_answer: { text: "No answer", mood: "calm" },
  busy: { text: "Busy", mood: "calm" },
  dial_failed: { text: "Dial failed", mood: "bad" },
  timeout: { text: "Timed out", mood: "bad" },
  drained: { text: "Drained", mood: "bad" },
  app_detached: { text: "App detached", mood: "bad" },
  error: { text: "Error", mood: "bad" },
};

/** `caller_hung_up` → `Caller hung up`. */
export function sentence(word: string): string {
  const words = word.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** How a call stands, in a word: wants a person, live, or how it ended. A waiting caller is the one row somebody has to act on. */
export function standingOf(line: Pick<SessionLine, "status" | "attention" | "end_reason">): Standing {
  if (line.status !== "ended") {
    if (line.attention?.status === "open") return { text: "Wants a person", mood: "warn" };
    return { text: line.status === "active" ? "Live" : sentence(line.status), mood: "good" };
  }
  if (line.end_reason === null) return { text: "Ended", mood: "calm" };
  return ENDINGS[line.end_reason] ?? { text: sentence(line.end_reason), mood: "calm" };
}
