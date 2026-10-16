/** Test's overview: the harness an agent goes through before a change ships and after — each station with its number, and the latest runs. */

import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { dayAndTime } from "../../lib/format";
import { Card, CardHead, Empty, Page, PageHead, Refused, Stat, Stats } from "../../ui";
import { useCases } from "../cases/use-cases";
import type { EvalRun } from "../evals/door";
import { RunTable } from "../evals/run-table";
import { useEvalRuns } from "../evals/use-eval-runs";
import { usePersonas } from "../personas/use-personas";
import { useRunStandings } from "../personas/use-run-standings";
import "./test-overview.css";

/** Goldens passing and failing in the newest run that has a matrix: a golden fails when any cell of it did. */
function tallyOf(run: EvalRun | undefined): { passing: number; failing: number } {
  const held = new Map<string, boolean>();
  for (const cell of run?.matrix?.runs ?? []) {
    const now = cell.scores.every((score) => score.passed);
    held.set(cell.golden, (held.get(cell.golden) ?? true) && now);
  }
  const passing = [...held.values()].filter(Boolean).length;
  return { passing, failing: held.size - passing };
}

/** One station of the harness: where it is, what it does, and its number right now. */
interface Station {
  name: string;
  to: string;
  does: string;
  now: ReactNode;
}

/**
 * Test is the harness: the callers written for the agent, the calls they make, the questions every
 * call is held to, the fixed questions replayed before a change ships, the real calls that broke,
 * and the lines the numbers must not cross. Each tab is one station; this page is all of them.
 */
export function TestOverview(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const base = `/a/${encodeURIComponent(agent)}`;
  const navigate = useNavigate();
  const runs = useEvalRuns(agent);
  const { listed } = useCases(agent);
  const { personas } = usePersonas(agent);
  const standings = useRunStandings(personas);
  const latest = runs.runs.find((run) => run.matrix !== null);
  const tally = tallyOf(latest);
  const simulated = Object.values(standings.by).reduce((sum, one) => sum + one.total, 0);
  const last = runs.runs[0];

  const stations: Station[] = [
    { name: "Personas", to: `${base}/personas`, does: "The callers written for the agent: a goal, a manner, the facts they know. A model plays each.", now: personas === null ? "…" : `${personas.length} written` },
    { name: "Simulations", to: `${base}/simulations`, does: "A persona on the line, in writing or out loud, watched here as it happens and judged at hang-up.", now: standings.read ? `${simulated} run` : "…" },
    { name: "Judges", to: `${base}/judges`, does: "The questions every call is held to at hang-up, each one asked of a model — Pinecall's, switched on or off, the org's and the agent's own.", now: "every call, every simulation" },
    { name: "Goldens", to: `${base}/goldens`, does: "Fixed questions replayed under every model you name: is a change safe to ship? The gate in CI.", now: latest === undefined ? "no run yet" : `${tally.passing} passing · ${tally.failing} failing` },
    { name: "Cases", to: `${base}/cases`, does: "A real call a judge broke on, kept whole: reproduce it, fix it where it belongs, approve it into the nightly.", now: listed === null ? "…" : `${listed.pending} waiting` },
    { name: "Monitors", to: `${base}/monitors`, does: "The numbers of the agent's calls watched over a window — latency, the judges, spend — and the line each must not cross.", now: "fires once a day" },
  ];

  return (
    <Page tight>
      <PageHead
        title="Test"
        ledeWidth={660}
        lede={`Everything ${agent} is held to, before a change ships and after: who calls it, what every call must do, what a change must not break, and the numbers that must not slip.`}
      />
      <Stats min={150}>
        <Stat size="small" label="Cases waiting" value={listed === null ? "—" : listed.pending} tone={listed !== null && listed.pending > 0 ? "red" : undefined} />
        <Stat size="small" label="Goldens passing" value={latest === undefined ? "—" : tally.passing} tone={latest === undefined ? undefined : "green"} />
        <Stat size="small" label="Goldens failing" value={latest === undefined ? "—" : tally.failing} tone={latest === undefined || tally.failing === 0 ? undefined : "red"} />
        <Stat size="small" label="Personas" value={personas === null ? "—" : personas.length} />
        <div className="ui-stat ui-stat-small">
          <div className="ui-stat-label">Last run</div>
          <div className="tov-last">{last === undefined ? "never" : dayAndTime(last.started_at)}</div>
        </div>
      </Stats>
      <Card pad>
        <CardHead title="The harness" meta="six stations, each a tab · a change goes left to right, a broken call comes back round" />
        <ol className="tov-stations">
          {stations.map((station, at) => (
            <li key={station.name} className="tov-station">
              <Link to={station.to} className="tov-station-link">
                <span className="tov-station-n">{at + 1}</span>
                <span className="tov-station-name">{station.name}</span>
                <span className="tov-station-does">{station.does}</span>
                <span className="tov-station-now">{station.now}</span>
              </Link>
            </li>
          ))}
        </ol>
      </Card>
      <Card>
        <CardHead title="Latest runs" meta={`${runs.runs.length} · the same rows pinecall runs list prints · a row opens it under Goldens`} />
        <Refused>{runs.error}</Refused>
        {runs.runs.length > 0 ? (
          <RunTable runs={runs.runs.slice(0, 8)} selected={null} onSelect={(id) => void navigate(`${base}/goldens?run=${encodeURIComponent(id)}`)} />
        ) : (
          <Empty>{runs.reading ? "Reading…" : "No run has been stored yet. A run appears here the moment one opens — from Goldens, a laptop or CI."}</Empty>
        )}
      </Card>
    </Page>
  );
}
