/** Hook for the rosters of the agents named: read a few at a time, each kept as it arrives. */

import { useCallback, useEffect, useState } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readCallers, readRuns, type Persona } from "../simulations/door";
import type { Roster } from "./fold";

// An org of forty agents is forty reads: this many are out at once, the rest wait their turn.
const AT_ONCE = 3;

export interface Rosters {
  /** By agent; an agent not in it yet is still being read. */
  rosters: ReadonlyMap<string, Roster>;
  /** A write answered with the agent's callers as they stand. */
  setCallers: (agent: string, callers: Persona[]) => void;
}

export function useRosters(agents: readonly string[]): Rosters {
  const credentials = useCredentials();
  const [rosters, setRosters] = useState<ReadonlyMap<string, Roster>>(new Map());
  const asked = agents.join("\n");

  useEffect(() => {
    let gone = false;
    setRosters(new Map());
    const waiting = asked === "" ? [] : asked.split("\n");
    const work = async (): Promise<void> => {
      for (let agent = waiting.shift(); agent !== undefined && !gone; agent = waiting.shift()) {
        const slug = agent;
        // The callers are the roster; its calls only say how each last went, and are drawn without when refused.
        const [callers, runs] = await Promise.allSettled([readCallers(credentials, slug), readRuns(credentials, [slug])]);
        if (gone) return;
        const roster: Roster = {
          agent: slug,
          callers: callers.status === "fulfilled" ? callers.value : null,
          runs: runs.status === "fulfilled" ? runs.value.runs : [],
          refused: callers.status === "fulfilled" ? null : saidBy(callers.reason),
        };
        setRosters((was) => new Map(was).set(slug, roster));
      }
    };
    for (let worker = 0; worker < AT_ONCE; worker += 1) void work();
    return () => {
      gone = true;
    };
  }, [credentials, asked]);

  const setCallers = useCallback((agent: string, callers: Persona[]): void => {
    setRosters((was) => new Map(was).set(agent, { agent, callers, runs: was.get(agent)?.runs ?? [], refused: null }));
  }, []);

  return { rosters, setCallers };
}
