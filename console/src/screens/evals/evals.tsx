/** Goldens, a tab of Test: the agent's goldens as transcripts, where each stands in the newest run, and every run — is a change safe to ship? */

import { useEffect, useState, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { inTheOtherWorld, WORLD } from "../../lib/mode";
import { Button, Card, CardHead, Empty, Page, PageHead, Refused, Stat, Stats } from "../../ui";
import type { EvalRun } from "./door";
import { GoldenList } from "./golden-list";
import { RunDetail } from "./run-detail";
import { RunTable } from "./run-table";
import { SuiteForm } from "./suite-form";
import { readGoldens, startSuite, type Listed, type Roster } from "./testing";
import { useEvalRuns } from "./use-eval-runs";
import "./evals.css";

/** Whether each golden held in a run: every judgment on it, under every model. */
function heldIn(run: EvalRun | undefined): Map<string, boolean> {
  const held = new Map<string, boolean>();
  for (const cell of run?.matrix?.runs ?? []) {
    const now = cell.scores.every((score) => score.passed);
    held.set(cell.golden, (held.get(cell.golden) ?? true) && now);
  }
  return held;
}

// All state lives in the URL (`?run=`, `?golden=`) so a regression can be shared as a link. How the agent's REAL
// calls are judged is Quality's; this is the goldens alone.
export function Evals(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const credentials = useCredentials();
  const [params, setParams] = useSearchParams();
  const runs = useEvalRuns(agent);
  const [roster, setRoster] = useState<Roster | null>(null);
  const [away, setAway] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  // Suites run through a developer's local class, so only the sandbox can start them.
  const suites = WORLD === "sandbox";

  useEffect(() => {
    let gone = false;
    readGoldens(credentials, agent).then(
      (read) => {
        if (!gone) setRoster(read);
      },
      (failed: unknown) => {
        if (!gone) setAway(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  const selected = params.get("run");
  const open = runs.runs.find((run) => run.id === selected) ?? null;
  const latest = runs.runs.find((run) => run.matrix !== null);
  const held = heldIn(latest);
  const goldens: Listed[] = roster !== null && roster.agent === agent ? roster.goldens : [];
  const names = goldens.length > 0 ? goldens.map((one) => one.name) : [...held.keys()];
  const holding = [...held.values()].filter(Boolean).length;
  const broken = held.size - holding;

  const select = (next: Record<string, string | null>): void => {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value === null) merged.delete(key);
      else merged.set(key, value);
    }
    setParams(merged);
  };

  const runAll = async (): Promise<void> => {
    setStarting(true);
    setRefused(null);
    try {
      const opened = await startSuite(credentials, {
        agent,
        goldens: goldens.map((one) => one.name),
        voice: false,
      });
      select({ run: opened });
    } catch (failed) {
      setRefused(failed instanceof Error ? failed.message : String(failed));
    } finally {
      setStarting(false);
    }
  };

  return (
    <Page width={1060} tight>
      <PageHead title="Goldens" lede="Scripted conversations, replayed before a change ships." />

      <Stats min={150}>
        <Stat size="small" label="Goldens" value={names.length === 0 ? "—" : names.length} />
        <Stat size="small" label="Held" value={latest === undefined ? "—" : holding} tone={latest === undefined ? undefined : "green"} />
        <Stat size="small" label="Broke" value={latest === undefined ? "—" : broken} tone={latest === undefined || broken === 0 ? undefined : "red"} />
        <div className="ui-stat ui-stat-small">
          <div className="ui-stat-label">Last run</div>
          <div className="ev-last">{runs.runs[0] === undefined ? "never" : dayAndTime(runs.runs[0].started_at)}</div>
        </div>
      </Stats>

      <Card>
        <CardHead
          title="Goldens"
          action={
            suites ? (
              goldens.length > 0 && (
                <Button kind="primary" size="sm" disabled={starting} onClick={() => void runAll()}>
                  {starting ? "Opening…" : "Run all"}
                </Button>
              )
            ) : (
              // A suite runs through a developer's own class, so it is started from the sandbox: the
              // same screen there, on the same key.
              <Button size="sm" onClick={() => window.location.assign(inTheOtherWorld(window.location.pathname))}>
                Run them in the sandbox
              </Button>
            )
          }
        />
        {names.length === 0 && (
          <Empty>
            {roster !== null && roster.agent !== agent
              ? roster.agent === null
                ? "No agent class where pinecall start runs."
                : `pinecall start runs in ${roster.agent}'s directory.`
              : away !== null && runs.runs.length === 0
                ? "No run yet. The goldens are read from pinecall start's directory."
                : "No goldens yet: write one in test/goldens."}
          </Empty>
        )}
        <GoldenList names={names} goldens={goldens} latest={latest} open={params.get("golden")} onOpen={(name) => select({ golden: name })} />
      </Card>

      <Refused>{refused}</Refused>

      {suites ? (
        <>
          {roster !== null && roster.agent === agent && goldens.length > 0 && <SuiteForm agent={agent} roster={roster} onOpened={(run) => select({ run })} />}
          <Card>
            <CardHead title="Runs" meta={String(runs.runs.length)} />
            <Refused>{runs.error}</Refused>
            {runs.runs.length > 0 ? <RunTable runs={runs.runs} selected={selected} onSelect={(id) => select({ run: id })} /> : <Empty>{runs.reading ? "Reading…" : "No run yet."}</Empty>}
          </Card>
          {open !== null && <RunDetail key={open.id} run={open} before={runs.runs[runs.runs.indexOf(open) + 1]} goldens={goldens} />}
        </>
      ) : (
        <Card>
          <CardHead title="Runs" meta={String(runs.runs.length)} />
          <Refused>{runs.error}</Refused>
          {runs.runs.length > 0 ? <RunTable runs={runs.runs} selected={selected} onSelect={(id) => select({ run: id })} /> : <Empty>{runs.reading ? "Reading…" : "No run yet. Suites run from the sandbox, a laptop or CI."}</Empty>}
        </Card>
      )}
      {!suites && open !== null && <RunDetail key={open.id} run={open} before={runs.runs[runs.runs.indexOf(open) + 1]} goldens={goldens} />}
    </Page>
  );
}
