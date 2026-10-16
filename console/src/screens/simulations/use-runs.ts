/** The simulations already run — the agent in view's, or every agent's — newest first, a page at a time; read again each time one starts. */

import { useCallback, useEffect, useState } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useHarnessAgents } from "../../lib/harness";
import { readSimulations, type PersonaRun } from "../personas/door";

export interface Runs {
  /** Null until the first page is read. */
  runs: PersonaRun[] | null;
  /** How many there are in all, past the pages read. */
  total: number;
  /** The older ones remain to be read. */
  more: boolean;
  asking: boolean;
  refused: string | null;
  older: () => void;
}

export function useRuns(inView: string, round: number): Runs {
  const credentials = useCredentials();
  // The agent in view's runs, or the org's agents' — the ones Viewing offers, and no other slug.
  const agents = useHarnessAgents(inView);
  const named = agents?.join("\n") ?? null;
  const [runs, setRuns] = useState<PersonaRun[] | null>(null);
  const [total, setTotal] = useState(0);
  const [next, setNext] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const page = useCallback(
    async (before?: string): Promise<void> => {
      if (named === null) return;
      // An org holding no agent has no runs to list: an empty name list would ask for every one.
      if (named === "") {
        setRuns([]);
        setTotal(0);
        setNext(null);
        return;
      }
      setAsking(true);
      try {
        const read = await readSimulations(credentials, named.split("\n"), before);
        setRuns((had) => (before === undefined ? read.runs : [...(had ?? []), ...read.runs]));
        setTotal(read.total);
        setNext(read.next);
        setRefused(null);
      } catch (failed) {
        setRefused(saidBy(failed));
      } finally {
        setAsking(false);
      }
    },
    [credentials, named],
  );

  // Read again whenever a simulation starts here, so the new one is at the top.
  useEffect(() => {
    void page();
  }, [page, round]);

  return { runs, total, more: next !== null, asking, refused, older: () => void (next !== null && page(next)) };
}
