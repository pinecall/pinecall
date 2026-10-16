/** Hook for a persona's simulation runs, paged. */

import { useCallback, useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readRuns, type PersonaRun } from "./door";

export interface Runs {
  runs: PersonaRun[] | null;
  /** Total runs, not just the loaded ones. */
  total: number;
  /** True while a page is loading. */
  asking: boolean;
  error: string | null;
  /** Append the next page; null when there is none. */
  more: (() => void) | null;
}

/** Runs newest first; changing the agent or `name` resets the list. */
export function usePersonaRuns(agent: string, name: string): Runs {
  const credentials = useCredentials();
  const [runs, setRuns] = useState<PersonaRun[] | null>(null);
  const [total, setTotal] = useState(0);
  const [next, setNext] = useState<string | null>(null);
  const [asking, setAsking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const said = (failed: unknown): string => (failed instanceof Error ? failed.message : String(failed));

  useEffect(() => {
    let gone = false;
    setRuns(null);
    setTotal(0);
    setNext(null);
    setAsking(true);
    setError(null);
    readRuns(credentials, agent, name).then(
      (read) => {
        if (gone) return;
        setRuns(read.runs);
        setTotal(read.total);
        setNext(read.next);
        setAsking(false);
      },
      (failed: unknown) => {
        if (gone) return;
        setError(said(failed));
        setAsking(false);
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, name]);

  // Use the gateway's `next` cursor so runs with equal timestamps are neither duplicated nor skipped.
  const readMore = useCallback((): void => {
    if (next === null) return;
    setAsking(true);
    setError(null);
    readRuns(credentials, agent, name, { before: next }).then(
      (read) => {
        setRuns((had) => [...(had ?? []), ...read.runs]);
        setTotal(read.total);
        setNext(read.next);
        setAsking(false);
      },
      (failed: unknown) => {
        setError(said(failed));
        setAsking(false);
      },
    );
  }, [credentials, agent, name, next]);

  return { runs, total, asking, error, more: next === null ? null : readMore };
}
