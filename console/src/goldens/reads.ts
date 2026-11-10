/** What the Goldens page reads: each agent's cases and runs, a few agents at a time, each kept as it arrives. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readCases, readRuns, type EvalCase, type Run } from "../test/door";

// How many agents are asked about at the same time.
const AT_ONCE = 3;

/** One agent's answer; `refused` is why a door of the two said no, and what it would have listed reads as nothing. */
export interface Read {
  cases: EvalCase[];
  runs: Run[];
  refused: string | null;
}

export interface Reads {
  /** By agent; an agent not in it yet is still being read. */
  read: ReadonlyMap<string, Read>;
  changeCases: (agent: string, change: (was: EvalCase[]) => EvalCase[]) => void;
  rereadRuns: (agent: string) => void;
}

type Credentials = ReturnType<typeof useCredentials>;

async function readAgent(credentials: Credentials, agent: string): Promise<Read> {
  const [cases, runs] = await Promise.allSettled([readCases(credentials, agent), readRuns(credentials, agent)]);
  const failed: unknown = cases.status === "rejected" ? cases.reason : runs.status === "rejected" ? runs.reason : null;
  return { cases: cases.status === "fulfilled" ? cases.value.cases : [], runs: runs.status === "fulfilled" ? runs.value : [], refused: failed === null ? null : saidBy(failed) };
}

/** The agents named, read `AT_ONCE` at a time in the order given; one already read is not asked about again. */
export function useReads(slugs: readonly string[]): Reads {
  const credentials = useCredentials();
  const [read, setRead] = useState<ReadonlyMap<string, Read>>(new Map());
  const arrived = useRef(new Set<string>());
  const wanted = slugs.join("\n");

  useEffect(() => {
    let gone = false;
    const queue = wanted === "" ? [] : wanted.split("\n").filter((slug) => !arrived.current.has(slug));
    const work = async (): Promise<void> => {
      for (let agent = queue.shift(); agent !== undefined && !gone; agent = queue.shift()) {
        const slug = agent;
        const said = await readAgent(credentials, slug);
        if (gone) return;
        arrived.current.add(slug);
        setRead((was) => new Map(was).set(slug, said));
      }
    };
    for (let worker = 0; worker < AT_ONCE; worker += 1) void work();
    return () => {
      gone = true;
    };
  }, [credentials, wanted]);

  const changeCases = useCallback((agent: string, change: (was: EvalCase[]) => EvalCase[]): void => {
    setRead((was) => {
      const held = was.get(agent);
      return held === undefined ? was : new Map(was).set(agent, { ...held, cases: change(held.cases) });
    });
  }, []);

  const rereadRuns = useCallback(
    (agent: string): void => {
      readRuns(credentials, agent).then(
        (runs) =>
          setRead((was) => {
            const held = was.get(agent);
            return held === undefined ? was : new Map(was).set(agent, { ...held, runs });
          }),
        () => undefined,
      );
    },
    [credentials],
  );

  return useMemo(() => ({ read, changeCases, rereadRuns }), [read, changeCases, rereadRuns]);
}
