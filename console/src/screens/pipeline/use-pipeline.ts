/** Hook for an agent's pipeline report. */

import { useEffect, useState } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readPipeline, type Report } from "./door";

export interface Pipeline {
  report: Report | null;
  error: string | null;
}

/** Read the pipeline the next call would use; changes only when settings change, so no stream. */
export function usePipeline(agent: string): Pipeline {
  const credentials = useCredentials();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    setReport(null);
    void readPipeline(credentials, agent).then(
      (read) => {
        if (!stopped) {
          setReport(read);
        }
      },
      (refused: unknown) => {
        if (!stopped) {
          setError(saidBy(refused));
        }
      },
    );
    return () => {
      stopped = true;
    };
  }, [agent, credentials]);

  return { report, error };
}
