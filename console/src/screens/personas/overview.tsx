/** What the screen shows before a caller is picked: how this agent's callers stand, and the callers themselves. */

import type { ReactNode } from "react";

import { ago } from "../../lib/format";
import { Button, Page, PageHead, Stat, Stats } from "../../ui";
import type { Persona, PersonaRun } from "./door";
import { whoseIs } from "../../lib/harness";
import { PersonaGrid } from "./grid";
import { NoCallers } from "./no-callers";
import { standingOf, type Standing, type Standings } from "./use-run-standings";

/**
 * This agent's callers as a standing, not as a second copy of the roster: how many there are, how
 * many times they have called it, when the last one was. The runs themselves are Simulations':
 * this screen is who calls, not how each call went.
 */
export function Overview({
  agent,
  agents,
  personas,
  standings,
  fixed,
  onNew,
  onGenerate,
  onSwitch,
}: {
  agent: string;
  /** How many agents a caller may be written for: none, and the library has no agent to be read through. */
  agents: number;
  personas: Persona[];
  standings: Standings;
  /** The class owns the roster: nothing is written here, and a generated caller is kept as a file. */
  fixed: boolean;
  onNew: () => void;
  onGenerate: () => void;
  onSwitch: (persona: Persona, on: boolean) => void;
}): ReactNode {
  const whose = whoseIs(agent);
  const runs = everyRun(standings.by);
  const never = personas.filter((one) => standings.by[standingOf(one)]?.total === 0);
  const newest = runs[0];

  if (personas.length === 0) {
    return (
      <Page>
        <PageHead title="Personas" />
        <NoCallers agent={agent} agents={agents} onNew={onNew} onGenerate={onGenerate} />
      </Page>
    );
  }

  return (
    <Page>
      <PageHead
        title="Personas"
        lede={
          <>
            The callers a model plays against {whose}, improvising every line.{" "}
            {fixed ? (
              <>
                Set by the class of {agent}: its own are code beside the class (<span className="ui-fixed">agents/{agent}/harness.*</span>, each an <span className="ui-fixed">ownPersona</span>), which of Pinecall's it plays is <span className="ui-fixed">personas({"{ on, own }"})</span> in the class, and a change is a commit.
              </>
            ) : (
              "Switch on Pinecall's, or write your own."
            )}
          </>
        }
        actions={
          <>
            {!fixed && (
              <Button size="base" kind="primary" onClick={onNew}>
                New persona
              </Button>
            )}
            {agent !== "" && (
              <Button size="base" onClick={onGenerate}>
                Generate…
              </Button>
            )}
          </>
        }
      />

      <Stats min={170}>
        <Stat label="Callers" value={personas.length} of={never.length === 0 ? undefined : `· ${never.length} never called`} />
        <Stat label="Runs" value={standings.read ? runs.length : "—"} of={standings.read ? "among the newest" : undefined} />
        <Stat label="Last run" value={newest === undefined ? "—" : ago(newest.started_at)} of={newest === undefined ? undefined : `· ${newest.persona}`} />
        <Stat label="On a call" value={runs.filter((one) => one.ended_at === null).length} />
      </Stats>

      <PersonaGrid agent={agent} personas={personas} standings={standings} onSwitch={onSwitch} />


    </Page>
  );
}

// Every caller's newest runs in one list, newest first; each run names the caller it was.
function everyRun(by: Record<string, Standing>): PersonaRun[] {
  return Object.values(by)
    .flatMap((standing) => standing.newest)
    .sort((one, other) => other.started_at - one.started_at);
}
