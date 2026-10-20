/** Hook for each judge's agreement with the labels people gave, by judge — the org's calls, or an agent's — read when the list changes. */

import { useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readAgreement, type Calibration, type JudgeAgreement, type Whose } from "./judges-door";

/** What the tiles draw: each labelled judge's agreement, and the lines every one is held to. */
export interface Agreement {
  judges: ReadonlyMap<string, JudgeAgreement>;
  labelsToJudge: number;
  agreesAtLeast: number;
}

// A refusal here hides nothing a tile needs: the judges are drawn without their agreement.
export function useAgreement(whose: Whose): Agreement | null {
  const credentials = useCredentials();
  const [read, setRead] = useState<Calibration | null>(null);

  useEffect(() => {
    let gone = false;
    setRead(null);
    readAgreement(credentials, whose).then(
      (answer) => {
        if (!gone) setRead(answer);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, whose]);

  if (read === null) return null;
  return { judges: new Map(read.judges.map((judge) => [judge.judge, judge])), labelsToJudge: read.labels_to_judge, agreesAtLeast: read.agrees_at_least };
}
