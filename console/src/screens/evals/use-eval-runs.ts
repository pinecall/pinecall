/** Hook for an agent's eval runs, read when the feed says one changed. */

import { useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { readRuns, type EvalRun } from "./door";

export interface EvalRuns {
  runs: EvalRun[];
  reading: boolean;
  error: string | null;
}

/** An agent's runs, read on open and whenever the feed says a run changed. */
export function useEvalRuns(agent: string): EvalRuns {
  const credentials = useCredentials();
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [reading, setReading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useFed(
    () => {
      readRuns(credentials, agent).then(
        (listed) => {
          setRuns(listed);
          setError(null);
          setReading(false);
        },
        (refused: unknown) => {
          setError(String(refused));
          setReading(false);
        },
      );
    },
    { types: ["run.changed"] },
    [agent],
  );

  return { runs, reading, error };
}
