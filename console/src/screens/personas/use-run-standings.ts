/** Hook for each persona's run count and newest runs, whichever agent each was written for. */

import { useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readRuns, type Persona, type PersonaRun } from "./door";

export interface Standing {
  total: number;
  newest: PersonaRun[];
}

export interface Standings {
  /** By `standingOf(persona)`: a name is one agent's, so the key is both. */
  by: Record<string, Standing>;
  read: boolean;
}

// Per-persona sample merged into the latest runs; totals stay exact regardless of the limit.
const A_FEW = 5;

/** The key a persona's standing is kept under. */
export function standingOf(persona: Pick<Persona, "agent" | "name">): string {
  return `${persona.agent}\u0000${persona.name}`;
}

/** Reads every persona in parallel, each against its own agent; failed reads are omitted from the map. */
export function useRunStandings(personas: readonly Persona[] | null): Standings {
  const credentials = useCredentials();
  const [standings, setStandings] = useState<Standings>({ by: {}, read: false });
  const asked = personas === null ? null : personas.map(standingOf).join("\n");

  useEffect(() => {
    if (asked === null) return;
    if (asked === "") {
      setStandings({ by: {}, read: true });
      return;
    }
    let gone = false;
    setStandings({ by: {}, read: false });
    void Promise.all(
      asked.split("\n").map(async (key): Promise<[string, Standing] | null> => {
        const [agent = "", name = ""] = key.split("\u0000");
        try {
          const page = await readRuns(credentials, agent, name, { limit: A_FEW });
          return [key, { total: page.total, newest: page.runs }];
        } catch {
          return null;
        }
      }),
    ).then((read) => {
      if (gone) return;
      setStandings({ by: Object.fromEntries(read.filter((one) => one !== null)), read: true });
    });
    return () => {
      gone = true;
    };
  }, [credentials, asked]);

  return standings;
}
