/** Hook that reads each finished call's `call.score`, a few at a time, and keeps every one it read. */

import { type CallScore } from "@pinecall/core/wire/events-call";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { useEffect, useRef, useState } from "react";

import type { Credentials } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readScore } from "@pinecall/core/score";
import { isLive } from "@pinecall/core/calls";

// Only the most recent ended calls are scored: one log read per call.
const A_SCREENFUL = 20;

// Reads in flight at once. Twenty at once, on every entry of the feed, took every connection of
// the gateway's pool on 2026-10-21 and the console was answered 503.
export const A_FEW = 4;

/** A finished call with its score, or the read error. */
export interface Scored {
  line: SessionLine;
  // Distinguishes "not read yet" from "read, no `call.score`".
  read: boolean;
  score: CallScore | null;
  refused: string | null;
}

/** A score kept: what was read, and how far the log had got when it was read. */
export interface Kept {
  scored: Scored;
  seq: number;
}

/**
 * The rows of `ended` that want a read: never read, or read with no score while the log has
 * moved since (the judges write the score after the call ends), and not already in flight.
 */
export function wanting(ended: readonly SessionLine[], held: ReadonlyMap<string, Kept>, inFlight: ReadonlySet<string>): SessionLine[] {
  return ended.filter((line) => {
    if (inFlight.has(line.call)) return false;
    // A list that says the call has no score yet is believed: the read would find none.
    if (line.score === null) return false;
    const kept = held.get(line.call);
    return kept === undefined || (kept.scored.score === null && line.last_seq > kept.seq);
  });
}

/** Run `read` over `lines`, `few` at a time, `kept` told of each as it lands. */
export async function aFewAtATime(lines: readonly SessionLine[], few: number, read: (line: SessionLine) => Promise<Scored>, kept: (line: SessionLine, scored: Scored) => void): Promise<void> {
  const queue = [...lines];
  const lane = async (): Promise<void> => {
    for (let line = queue.shift(); line !== undefined; line = queue.shift()) kept(line, await read(line));
  };
  await Promise.all(Array.from({ length: Math.min(few, queue.length) }, lane));
}

/** Scores for the ended calls among `lines`; each is kept as it lands, and read again only while it has none. */
export function useScores(lines: SessionLine[]): Scored[] {
  const credentials = useCredentials();
  const held = useRef<Map<string, Kept>>(new Map());
  const inFlight = useRef<Set<string>>(new Set());
  const [scored, setScored] = useState<ReadonlyMap<string, Kept>>(held.current);
  const ended = lines.filter((line) => !isLive(line)).slice(0, A_SCREENFUL);
  // Keyed on content, not array identity: `lines` is a new array on every poll.
  const wanted = ended.map((line) => `${line.call}@${line.last_seq}`).join(" ");

  useEffect(() => {
    let gone = false;
    const asked = wanting(ended, held.current, inFlight.current);
    for (const line of asked) inFlight.current.add(line.call);
    // A read outlasts the effect that started it: what lands is kept, whatever the list says now.
    void aFewAtATime(
      asked,
      A_FEW,
      (line) => scoreOf(credentials, line),
      (line, row) => {
        inFlight.current.delete(line.call);
        held.current.set(line.call, { scored: row, seq: line.last_seq });
        if (!gone) setScored(new Map(held.current));
      },
    );
    return () => {
      gone = true;
    };
  }, [wanted, credentials]);

  return ended.map((line) => scored.get(line.call)?.scored ?? unread(line));
}

// Errors stay per row so one unreadable entry doesn't fail the whole list.
async function scoreOf(credentials: Credentials, line: SessionLine): Promise<Scored> {
  try {
    const score = await readScore(credentials, line.call, line.last_seq);
    return { line, read: true, score, refused: null };
  } catch (refused) {
    return { line, read: true, score: null, refused: String(refused) };
  }
}

function unread(line: SessionLine): Scored {
  return { line, read: false, score: null, refused: null };
}
