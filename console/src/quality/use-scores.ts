/** Reads each finished call's score, a few at a time, and keeps every one it read. */

import { useEffect, useRef, useState } from "react";

import type { Credentials } from "@pinecall/core/api";
import { isLive } from "@pinecall/core/calls";
import { useCredentials } from "@pinecall/core/credentials";
import { readScore } from "@pinecall/core/score";
import { type CallScore } from "@pinecall/core/wire/events-call";
import { type SessionLine } from "@pinecall/core/wire/rest";

// Only the newest ended calls are read: one request per call.
const A_SCREENFUL = 20;

// Reads in flight at once: twenty together once took every connection of the gateway's pool.
const A_FEW = 4;

/** A finished call with its score; `read` tells "not read yet" from "read, and it has none". */
export interface Scored {
  line: SessionLine;
  read: boolean;
  score: CallScore | null;
}

interface Kept {
  scored: Scored;
  /** How far the call's log had got when it was read. */
  seq: number;
}

/** The calls that want a read: never read, or read with no score while the log has moved since, and not already asked. */
function wanting(ended: readonly SessionLine[], held: ReadonlyMap<string, Kept>, inFlight: ReadonlySet<string>): SessionLine[] {
  return ended.filter((line) => {
    if (inFlight.has(line.call)) return false;
    // A list that says the call has no score yet is believed: the read would find none.
    if (line.score === null) return false;
    const kept = held.get(line.call);
    return kept === undefined || (kept.scored.score === null && line.last_seq > kept.seq);
  });
}

async function aFewAtATime(lines: readonly SessionLine[], read: (line: SessionLine) => Promise<Scored>, kept: (line: SessionLine, scored: Scored) => void): Promise<void> {
  const queue = [...lines];
  const lane = async (): Promise<void> => {
    for (let line = queue.shift(); line !== undefined; line = queue.shift()) kept(line, await read(line));
  };
  await Promise.all(Array.from({ length: Math.min(A_FEW, queue.length) }, lane));
}

// A call whose log cannot be read is a row with no score, never a failed list.
async function scoreOf(credentials: Credentials, line: SessionLine): Promise<Scored> {
  try {
    return { line, read: true, score: await readScore(credentials, line.call, line.last_seq) };
  } catch {
    return { line, read: true, score: null };
  }
}

/** The scores of the newest ended calls among `lines`, each kept as it lands and read again only while it has none. */
export function useScores(lines: readonly SessionLine[]): Scored[] {
  const credentials = useCredentials();
  const held = useRef<Map<string, Kept>>(new Map());
  const inFlight = useRef<Set<string>>(new Set());
  const [scored, setScored] = useState<ReadonlyMap<string, Kept>>(held.current);
  const ended = lines.filter((line) => !isLive(line)).slice(0, A_SCREENFUL);
  // By what the list holds, not by the array: `lines` is a new one on every read of the floor.
  const wanted = ended.map((line) => `${line.call}@${line.last_seq}`).join(" ");

  useEffect(() => {
    let gone = false;
    const asked = wanting(ended, held.current, inFlight.current);
    for (const line of asked) inFlight.current.add(line.call);
    // A read outlasts the effect that started it: what lands is kept, whatever the list says now.
    void aFewAtATime(
      asked,
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

  return ended.map((line) => scored.get(line.call)?.scored ?? { line, read: false, score: null });
}
