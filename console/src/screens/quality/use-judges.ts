/** Hook for the judges one list holds — the org's, or an agent's — loaded when it changes. */

import { useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readJudges, type JudgeRow, type Whose } from "./judges-door";

export function useJudges(whose: Whose): {
  judges: JudgeRow[] | null;
  error: string | null;
  setJudges: (judges: JudgeRow[]) => void;
} {
  const credentials = useCredentials();
  const [judges, setJudges] = useState<JudgeRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    setJudges(null);
    setError(null);
    readJudges(credentials, whose).then(
      (read) => {
        if (!gone) setJudges(read);
      },
      (failed: unknown) => {
        if (!gone) setError(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, whose]);

  return { judges, error, setJudges };
}
