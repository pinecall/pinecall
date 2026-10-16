/** Hook that reads each finished call's `call.score` once. */

import { type CallScore } from "@pinecall/core/wire/events-call";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { useEffect, useRef, useState } from "react";

import type { Credentials } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readScore } from "@pinecall/core/score";
import { isLive } from "@pinecall/core/calls";

// Only the most recent ended calls are scored: one log read per call.
const A_SCREENFUL = 20;

/** A finished call with its score, or the read error. */
export interface Scored {
  line: SessionLine;
  // Distinguishes "not read yet" from "read, no `call.score`".
  read: boolean;
  score: CallScore | null;
  refused: string | null;
}

/** Scores for the ended calls among `lines`; each is read once and cached, since it never changes. */
export function useScores(lines: SessionLine[]): Scored[] {
  const credentials = useCredentials();
  const held = useRef<Map<string, Scored>>(new Map());
  const [scored, setScored] = useState<ReadonlyMap<string, Scored>>(held.current);
  const ended = lines.filter((line) => !isLive(line)).slice(0, A_SCREENFUL);
  // Keyed on content, not array identity: `lines` is a new array on every poll.
  const wanted = ended.map((line) => `${line.call}@${line.last_seq}`).join(" ");

  useEffect(() => {
    let stopped = false;
    const unread = ended.filter((line) => !held.current.has(line.call));

    void (async () => {
      const rows = await Promise.all(unread.map((line) => scoreOf(credentials, line)));
      if (stopped || rows.length === 0) {
        return;
      }
      for (const row of rows) {
        held.current.set(row.line.call, row);
      }
      setScored(new Map(held.current));
    })();

    return () => {
      stopped = true;
    };
  }, [wanted, credentials]);

  return ended.map((line) => scored.get(line.call) ?? unread(line));
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
