/** What the screen shows before a caller is picked: how this agent's callers stand, and the callers themselves. */

import type { ReactNode } from "react";

import { ago } from "../../lib/format";
import { Button, Card, Empty, Page, PageHead, Stat, Stats } from "../../ui";
import type { Persona, PersonaRun } from "./door";
import { whoseIs } from "../../lib/harness";
import { PersonaGrid } from "./grid";
import { standingOf, type Standing, type Standings } from "./use-run-standings";

/**
 * This agent's callers as a standing, not as a second copy of the roster: how many there are, how
 * many times they have called it, when the last one was. The runs themselves are Simulations':
 * this screen is who calls, not how each call went.
 */
export function Overview({
  agent,
  personas,
  standings,
  onNew,
  onGenerate,
  onSwitch,
}: {
  agent: string;
  personas: Persona[];
  standings: Standings;
  onNew: () => void;
  onGenerate: () => void;
  onSwitch: (persona: Persona, on: boolean) => void;
}): ReactNode {
  const whose = whoseIs(agent);
  const runs = everyRun(standings.by);
  const never = personas.filter((one) => standings.by[standingOf(one)]?.total === 0);
  const newest = runs[0];

  if (personas.length === 0) {
    return <NoCallers onNew={onNew} />;
  }

  return (
    <Page>
      <PageHead
        title="Personas"
        lede={
          <>
            The callers a model plays against {whose}, improvising every line — in Simulations, or in <span className="ui-fixed">pinecall simulate</span>. Switch on Pinecall's, or write your own.
          </>
        }
        actions={
          <>
            <Button size="base" kind="primary" onClick={onNew}>
              New persona
            </Button>
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

// An agent with nobody written yet is the one place the whole sentence belongs: there is nothing to
// show, and what a persona IS is exactly what the person is missing.
function NoCallers({ onNew }: { onNew: () => void }): ReactNode {
  return (
    <Page>
      <PageHead
        title="Personas"
        lede="A persona is somebody who calls this business wanting something: a goal, a manner, and the few facts they may state about themselves. A model plays them against an agent and improvises every line — there is no script to write."
        ledeWidth={640}
        actions={
          <Button kind="primary" size="base" onClick={onNew}>
            New persona
          </Button>
        }
      />
      <Card>
        <Empty>No callers yet. The first one takes a minute: what they want, how they talk, and what they know about themselves.</Empty>
      </Card>
    </Page>
  );
}

// Every caller's newest runs in one list, newest first; each run names the caller it was.
function everyRun(by: Record<string, Standing>): PersonaRun[] {
  return Object.values(by)
    .flatMap((standing) => standing.newest)
    .sort((one, other) => other.started_at - one.started_at);
}
