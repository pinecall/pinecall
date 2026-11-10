/** What every page of the console reads: who is signed in, their orgs, the agents held, and the calls. */

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { readHeldAgents } from "@pinecall/core/agents";
import { useCredentials } from "@pinecall/core/credentials";
import { orgsOf, type OrgOf } from "@pinecall/core/login";
import { useFloor } from "@pinecall/core/use-floor";
import { whoami, type Whose } from "@pinecall/core/whoami";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { readHosted, type Hosted } from "../apps/door";
import { useOperator } from "./operator";

export interface Org {
  whose: Whose | null;
  orgs: OrgOf[] | null;
  /** One row per agent, newest list first. */
  agents: HeldAgent[];
  agentsRead: boolean;
  /** The names built in Studio, running or stopped: everything else is an app. */
  studio: ReadonlySet<string>;
  /** What the box hosts for the org; null until read, and for a key that may not read it. */
  hosted: readonly Hosted[] | null;
  lines: SessionLine[];
  live: SessionLine[];
  /** Whether the person runs the box; null while asking. */
  operator: boolean | null;
}

const Held = createContext<Org | null>(null);

// A key that may see every corner gets one row per copy: the list names an agent once.
function oncePerSlug(held: readonly HeldAgent[]): HeldAgent[] {
  return [...new Map(held.map((one) => [one.slug, one])).values()];
}

export function OrgProvider({ children }: { children: ReactNode }): ReactNode {
  const credentials = useCredentials();
  const floor = useFloor(50);
  const operator = useOperator();
  const [whose, setWhose] = useState<Whose | null>(null);
  const [orgs, setOrgs] = useState<OrgOf[] | null>(null);
  const [agents, setAgents] = useState<HeldAgent[]>([]);
  const [agentsRead, setAgentsRead] = useState(false);
  const [hosted, setHosted] = useState<readonly Hosted[] | null>(null);

  useEffect(() => {
    let gone = false;
    whoami(credentials).then((said) => !gone && setWhose(said), () => undefined);
    orgsOf(credentials).then((said) => !gone && setOrgs(said), () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials]);

  useEffect(() => {
    let gone = false;
    readHeldAgents(credentials).then(
      (said) => {
        if (gone) return;
        setAgents(oncePerSlug(said));
        setAgentsRead(true);
      },
      () => !gone && setAgentsRead(true),
    );
    return () => {
      gone = true;
    };
  }, [credentials, floor.agentsChanged]);

  // A key that may not read what is hosted still knows the Studio agents that are running.
  useEffect(() => {
    let gone = false;
    readHosted(credentials).then((said) => !gone && setHosted(said), () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials, floor.agentsChanged]);

  const studio = useMemo(() => new Set([...(hosted ?? []).filter((one) => one.kind === "studio").map((one) => one.name), ...agents.filter((one) => one.kind === "studio").map((one) => one.slug)]), [hosted, agents]);
  const value = useMemo<Org>(() => ({ whose, orgs, agents, agentsRead, studio, hosted, lines: floor.lines, live: floor.lines.filter((line) => line.live), operator }), [whose, orgs, agents, agentsRead, studio, hosted, floor.lines, operator]);
  return <Held value={value}>{children}</Held>;
}

export function useOrg(): Org {
  const held = useContext(Held);
  if (held === null) throw new Error("this page was mounted outside the console");
  return held;
}
