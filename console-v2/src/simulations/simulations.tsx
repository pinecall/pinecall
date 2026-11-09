/** Simulations, the same page as Apps and Knowledge: the calls and comparisons already made in a list, and beside it the one open, or the form that places the next. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago, lengthOf, percent } from "../lib/format";
import { useOrg } from "../lib/org";
import { PageHead } from "../shell/page-head";
import { Board } from "./board";
import { Composer, type Typical } from "./composer";
import { readRuns, setupKey, standingOf, type PersonaRun, type Standing } from "./door";
import { ResultsPanel, useWatched, WatchActions, WatchBody } from "./watch";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "./simulations.css";

const HOME = "/simulations";
// A call on the line is read again this often, so its row says how it ended without a reload.
const A_CALL_IS_ASKED_EVERY_MS = 5000;

const DOTS: Record<Standing, string> = { live: "app-dot app-dot-warn sim-dot-live", held: "app-dot app-dot-good", broke: "app-dot app-dot-bad", unjudged: "app-dot app-dot-calm" };
const SAID: Record<Standing, string> = { live: "On the line", held: "Every judge held", broke: "A judge broke", unjudged: "Not judged" };

const rowClass = ({ isActive }: { isActive: boolean }): string => (isActive ? "app-row app-row-on" : "app-row");

/** What the list draws: one call, or the calls of one comparison as one row. */
type Listed = { kind: "run"; run: PersonaRun } | { kind: "comparison"; id: string; runs: PersonaRun[] };

function listed(runs: readonly PersonaRun[]): Listed[] {
  const rows: Listed[] = [];
  const compared = new Map<string, PersonaRun[]>();
  for (const run of runs) {
    if (run.comparison === null) {
      rows.push({ kind: "run", run });
      continue;
    }
    const mine = compared.get(run.comparison);
    if (mine !== undefined) {
      mine.push(run);
      continue;
    }
    const first = [run];
    compared.set(run.comparison, first);
    rows.push({ kind: "comparison", id: run.comparison, runs: first });
  }
  return rows;
}

function RunRow({ run }: { run: PersonaRun }): ReactNode {
  const standing = standingOf(run);
  const under = standing === "live" ? "on the line now" : [ago(run.started_at), lengthOf(run.started_at, run.ended_at), run.score !== null && run.score.judged > 0 ? `${run.score.held}/${run.score.judged} held` : null].filter((part) => part !== null).join(" · ");
  return (
    <NavLink to={`${HOME}/${run.call}`} className={rowClass}>
      <span className="app-row-top">
        <span className="dash-clip">{run.persona ?? "A caller"}</span>
        <span className={DOTS[standing]} title={SAID[standing]} aria-hidden="true" />
      </span>
      <span className="app-row-under dash-clip">
        {run.agent} · {under}
      </span>
    </NavLink>
  );
}

function ComparisonRow({ id, runs }: { id: string; runs: PersonaRun[] }): ReactNode {
  const live = runs.some((run) => run.ended_at === null);
  const models = new Set(runs.map((run) => setupKey(run.against ?? {}))).size;
  const tasks = new Set(runs.map((run) => run.persona)).size;
  const first = runs.at(-1) ?? runs[0];
  return (
    <NavLink to={`${HOME}/compare/${id}`} className={rowClass}>
      <span className="app-row-top">
        <span className="dash-clip">
          {models} models, {tasks} {tasks === 1 ? "task" : "tasks"}
        </span>
        {live ? <span className={DOTS.live} title={SAID.live} aria-hidden="true" /> : <span className="dash-tag">Compared</span>}
      </span>
      <span className="app-row-under dash-clip">
        {first?.agent} · {live ? "on the line now" : ago(first?.started_at ?? null)}
      </span>
    </NavLink>
  );
}

/** One call open: its buttons in the header, as Agents has its own, and its results docked beside it. */
function OpenCall({ call, run, list }: { call: string; run: PersonaRun | undefined; list: ReactNode }): ReactNode {
  const watched = useWatched(call);
  const [results, setResults] = useState(true);
  return (
    <>
      <PageHead open={run?.persona ?? "A call"}>
        <WatchActions watched={watched} results={results} onResults={() => setResults(!results)} />
      </PageHead>
      <div className="app-layout sim-layout">
        {list}
        <div className="app-open">
          <WatchBody watched={watched} run={run} />
        </div>
      </div>
      {results && <ResultsPanel watched={watched} onClose={() => setResults(false)} />}
    </>
  );
}

export function SimulationsPage(): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const { call, comparison } = useParams();
  const [params] = useSearchParams();
  const { agents, agentsRead } = useOrg();
  const slugs = useMemo(() => agents.map((one) => one.slug), [agents]);
  const named = slugs.join("\n");
  const [runs, setRuns] = useState<PersonaRun[] | null>(null);
  const [total, setTotal] = useState(0);
  const [next, setNext] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => {
    // An org holding no agent has no run to list: no name at all would ask for every one.
    if (named === "") {
      if (agentsRead) setRuns([]);
      return;
    }
    try {
      const read = await readRuns(credentials, named.split("\n"));
      setRuns(read.runs);
      setTotal(read.total);
      setNext(read.next);
      setRefused(null);
    } catch (failed) {
      setRuns((was) => was ?? []);
      setRefused(saidBy(failed));
    }
  }, [credentials, named, agentsRead]);

  useEffect(() => {
    void reread();
  }, [reread]);

  const anyLive = (runs ?? []).some((run) => run.ended_at === null);
  useEffect(() => {
    if (!anyLive) return;
    const timer = window.setInterval(() => void reread(), A_CALL_IS_ASKED_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [anyLive, reread]);

  const older = async (): Promise<void> => {
    if (next === null) return;
    try {
      const read = await readRuns(credentials, slugs, next);
      setRuns((was) => [...(was ?? []), ...read.runs]);
      setNext(read.next);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  // One call started is the one to watch; several stay in the list, each live until it ends.
  const started = async (calls: string[]): Promise<void> => {
    await reread();
    const only = calls.length === 1 ? calls[0] : undefined;
    if (only !== undefined) void navigate(`${HOME}/${only}`);
  };

  const compared = async (id: string): Promise<void> => {
    await reread();
    void navigate(`${HOME}/compare/${id}`);
  };

  const ended = (runs ?? []).filter((run) => run.ended_at !== null);
  const typical: Typical = {
    seconds: ended.length === 0 ? null : ended.reduce((sum, run) => sum + ((run.ended_at ?? run.started_at) - run.started_at), 0) / ended.length,
    usd: ended.length === 0 ? null : ended.reduce((sum, run) => sum + (run.cost_usd ?? 0) + run.caller_cost_usd, 0) / ended.length,
  };
  const judged = ended.filter((run) => run.score !== null && run.score.judged > 0);
  const held = judged.filter((run) => run.score?.passed === true).length;

  const list = (
    <aside className="app-list" aria-label="Simulations">
      <div className="app-list-head">
        <span className="app-list-title">Simulations</span>
        <span className="dash-quiet">{runs === null ? "" : total}</span>
        <NavLink to={HOME} end className="app-button sim-new-button">
          New
        </NavLink>
      </div>
      {judged.length > 0 && (
        <div className="sim-held" title={`${held} of the last ${judged.length} judged calls held`}>
          <span className="sim-held-track">
            <span style={{ width: `${(held / judged.length) * 100}%` }} />
          </span>
          <span className="dash-quiet">{percent(held / judged.length)} held</span>
        </div>
      )}
      <div className="app-rows">
        {listed(runs ?? []).map((row) => (row.kind === "run" ? <RunRow key={row.run.call} run={row.run} /> : <ComparisonRow key={row.id} id={row.id} runs={row.runs} />))}
        {runs !== null && runs.length === 0 && <p className="dash-quiet app-none">No simulation yet. The first one shows up here.</p>}
        {next !== null && (
          <button type="button" className="sim-link sim-older" onClick={() => void older()}>
            Show older
          </button>
        )}
      </div>
    </aside>
  );

  if (call !== undefined) return <OpenCall key={call} call={call} run={runs?.find((run) => run.call === call)} list={list} />;

  return (
    <>
      <PageHead open={comparison === undefined ? undefined : "Comparison"} />
      <div className="app-layout sim-layout">
        {list}
        <div className="app-open">
          {refused !== null && <p className="app-refused app-open-note">{refused}</p>}
          {comparison !== undefined ? (
            <div className="app-main">
              <Board key={comparison} comparison={comparison} />
            </div>
          ) : (
            <div className="app-main sim-main">{agentsRead ? <Composer agents={slugs} asked={params.get("agent")} typical={typical} onStarted={(calls) => void started(calls)} onCompared={(id) => void compared(id)} /> : <p className="dash-quiet">Reading…</p>}</div>
          )}
        </div>
      </div>
    </>
  );
}
