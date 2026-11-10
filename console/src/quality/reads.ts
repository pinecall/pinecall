/** What Quality reads once per agent in view: the judges, the case groups with the cases waiting, and the newest golden runs. */

import { useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readCases, readGroups, readJudges, readSuites, type CaseGroup, type EvalCase, type JudgeRow, type Suite } from "./door";

/** The judges of the agent's calls, or the org's with ""; null until read, and for a key the door refuses. */
export function useJudges(agent: string): JudgeRow[] | null {
  const credentials = useCredentials();
  const [judges, setJudges] = useState<JudgeRow[] | null>(null);
  useEffect(() => {
    let gone = false;
    setJudges(null);
    readJudges(credentials, agent).then(
      (read) => {
        if (!gone) setJudges(read);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);
  return judges;
}

export interface Cases {
  /** The groups a judge's breaks fall in; null until read. */
  groups: CaseGroup[] | null;
  cases: EvalCase[];
}

/** The agent's case groups and cases, or every agent's with "". A refusal leaves both unread: the page draws without them. */
export function useCases(agent: string): Cases {
  const credentials = useCredentials();
  const [read, setRead] = useState<Cases>({ groups: null, cases: [] });
  useEffect(() => {
    let gone = false;
    setRead({ groups: null, cases: [] });
    Promise.all([readGroups(credentials, agent), readCases(credentials, agent)]).then(
      ([groups, cases]) => {
        if (!gone) setRead({ groups, cases });
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);
  return read;
}

/** Each agent's newest finished golden run; empty while asked, and for a key the door refuses. */
export function useSuites(): readonly Suite[] {
  const credentials = useCredentials();
  const [suites, setSuites] = useState<readonly Suite[]>([]);
  useEffect(() => {
    let gone = false;
    readSuites(credentials).then(
      (read) => {
        if (!gone) setSuites(read);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);
  return suites;
}
