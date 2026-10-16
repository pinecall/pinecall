/** One agent's cases, or every agent's, read once, and set again by what a decision answers. */

import { useCallback, useEffect, useState } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readCases, readGroups, type CaseGroup, type EvalCase, type Listed } from "./door";

export interface Cases {
  listed: Listed | null;
  /** The cases grouped by the judge that broke them, the pending first; null while asked. */
  groups: CaseGroup[] | null;
  /** Why the gateway would not answer, while it would not. */
  asking: string | null;
  /** A case as a decision answered it: replaced in the list, and the count of what waits redone. */
  decided: (kept: EvalCase) => void;
  /** A group as a door answered it: replaced; decided whole, its cases read again. */
  grouped: (group: CaseGroup) => void;
}

export function useCases(agent: string): Cases {
  const credentials = useCredentials();
  const [listed, setListed] = useState<Listed | null>(null);
  const [groups, setGroups] = useState<CaseGroup[] | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  // Decided whole, a group's cases change under the list: both are read again.
  const [round, setRound] = useState(0);

  useEffect(() => {
    let live = true;
    setListed(null);
    Promise.all([readCases(credentials, agent), readGroups(credentials, agent)])
      .then(([read, grouped]) => live && (setListed(read), setGroups(grouped), setAsking(null)))
      .catch((failed: unknown) => live && setAsking(saidBy(failed)));
    return () => {
      live = false;
    };
  }, [credentials, agent, round]);

  const decided = useCallback((kept: EvalCase): void => {
    setListed((was) => {
      if (was === null) return was;
      const cases = was.cases.map((each) => (each.id === kept.id ? kept : each));
      return { ...was, cases, pending: cases.filter((each) => each.status === "pending").length };
    });
  }, []);

  const grouped = useCallback((group: CaseGroup): void => {
    setGroups((was) => (was === null ? was : was.map((each) => (each.id === group.id ? group : each))));
    if (group.status !== "pending") setRound((was) => was + 1);
  }, []);

  return { listed, groups, asking, decided, grouped };
}
