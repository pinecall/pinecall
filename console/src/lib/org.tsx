/** Org context shared by all screens: calls, agents, orgs, insights, operator flag. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { bySlug, meIn } from "./corners";
import { useInsights, type Insights } from "./insights";
import { orgsOf, type OrgOf } from "@pinecall/core/login";
import { useOperator } from "./operator";
import type { Connection } from "@pinecall/core/stream";
import { useFloor } from "@pinecall/core/use-floor";
import { useHeldAgents } from "./use-held-agents";
import { useWhoami } from "./whoami";

// One page of the sessions door; a single subscription feeds the sidebar, home and floor.
const ROWS = 200;

export interface Org {
  /** Calls, newest first, and the live subset. */
  lines: SessionLine[];
  live: SessionLine[];
  connection: Connection;
  floorError: string | null;
  /** Every held copy, and one per slug preferring the reader's own. */
  held: HeldAgent[];
  agents: HeldAgent[];
  agentsLoaded: boolean;
  agentsError: string | null;
  /** The person's orgs; null for a key without a person, or while loading. */
  orgs: OrgOf[] | null;
  /** The key's org, from `orgs`. */
  here: OrgOf | null;
  insights: Insights | null;
  /** Whether the person is a box operator; null while loading. */
  operator: boolean | null;
}

const Held = createContext<Org | null>(null);

export function OrgProvider({ children }: { children: ReactNode }): ReactNode {
  const credentials = useCredentials();
  const whose = useWhoami();
  const floor = useFloor(ROWS);
  const insights = useInsights();
  const operator = useOperator();
  const held = useHeldAgents(floor.agentsChanged);
  const [orgs, setOrgs] = useState<OrgOf[] | null>(null);

  useEffect(() => {
    let gone = false;
    orgsOf(credentials).then(
      (listed) => {
        if (!gone) setOrgs(listed);
      },
      () => {
        if (!gone) setOrgs(null);
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const me = meIn(whose);
  const value = useMemo<Org>(
    () => ({
      lines: floor.lines,
      live: floor.lines.filter((line) => line.live),
      connection: floor.connection,
      floorError: floor.error,
      held: held.agents,
      agents: bySlug(held.agents, me),
      agentsLoaded: held.loaded,
      agentsError: held.error,
      orgs,
      here: orgs?.find((one) => one.here) ?? null,
      insights,
      operator,
    }),
    [floor.lines, floor.connection, floor.error, held.agents, held.loaded, held.error, orgs, me, insights, operator],
  );
  return <Held value={value}>{children}</Held>;
}

/** The shared org; throws outside the shell. */
export function useOrg(): Org {
  const held = useContext(Held);
  if (held === null) throw new Error("a screen was mounted outside the shell's org");
  return held;
}
