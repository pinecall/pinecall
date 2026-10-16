/** Summarise a contact's thread for the inbox aside. */

import { type SessionFlag, type SessionLine } from "@pinecall/core/wire/rest";

export interface Standing {
  conversations: number;
  /** Total seconds over ended calls only. */
  seconds: number;
  first: number | null;
  last: number | null;
  /** Distinct channels, newest call first. */
  channels: string[];
  /** Judges that held, over all judged calls. */
  held: number;
  judged: number;
  /** Distinct flags across the calls. */
  flags: SessionFlag[];
  live: boolean;
}

/** Computed from the already-listed lines, so the aside cannot contradict the list. */
export function standingOf(lines: readonly SessionLine[]): Standing {
  const standing: Standing = { conversations: lines.length, seconds: 0, first: null, last: null, channels: [], held: 0, judged: 0, flags: [], live: false };
  for (const line of lines) {
    if (line.started_at !== null && line.ended_at !== null) standing.seconds += Math.max(0, line.ended_at - line.started_at);
    if (line.started_at !== null) {
      standing.first = standing.first === null ? line.started_at : Math.min(standing.first, line.started_at);
      standing.last = standing.last === null ? line.started_at : Math.max(standing.last, line.started_at);
    }
    if (line.channel !== null && !standing.channels.includes(line.channel)) standing.channels.push(line.channel);
    if (line.score != null) {
      standing.held += line.score.held;
      standing.judged += line.score.judged;
    }
    for (const flag of line.flags ?? []) if (!standing.flags.includes(flag)) standing.flags.push(flag);
    if (line.status !== "ended") standing.live = true;
  }
  return standing;
}

// Display labels for the gateway's SessionFlag values (rest.json).
const FLAGS: Record<SessionFlag, string> = {
  escalated: "a person took part",
  low_score: "a judge broke",
  promise: "a promise was made",
};

/** Display label for a flag. */
export function flagReads(flag: SessionFlag): string {
  return FLAGS[flag];
}
