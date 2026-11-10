/** Simulations, the same page as Apps and Knowledge: the calls and comparisons already made in a list, and beside it the one open, or the form that places the next; in production, a check call's. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { AvatarOf, PersonaAvatar } from "../apps/avatar";
import { ago, dayLabel, lengthOf, percent, utcDay } from "../lib/format";
import { useOrg } from "../lib/org";
import { WORLD } from "../lib/world";
import { PageHead } from "../shell/page-head";
import { Board } from "./board";
import { CheckCall } from "./check";
import { Composer, type Typical } from "./composer";
import { readRuns, setupKey, standingOf, type PersonaRun, type Standing } from "./door";
import { ResultsPanel, useWatched, WatchActions, WatchBody } from "./watch";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "./simulations.css";

const HOME = "/simulations";
// Production takes one caller, one call: a check of the agent as it is deployed, on a form of its own.
const CHECKING = WORLD === "production";
const LISTED = CHECKING ? "Checks" : "Simulations";
// A call on the line is read again this often, so its row says how it ended without a reload.
const A_CALL_IS_ASKED_EVERY_MS = 5000;

const DOTS: Record<Standing, string> = { live: "app-dot app-dot-warn sim-dot-live", held: "app-dot app-dot-good", broke: "app-dot app-dot-bad", unjudged: "app-dot app-dot-calm" };
const SAID: Record<Standing, string> = { live: "On the line", held: "Every judge held", broke: "A judge broke", unjudged: "Not judged" };

const rowClass = ({ isActive }: { isActive: boolean }): string => (isActive ? "app-row app-row-worn app-row-on" : "app-row app-row-worn");

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

/** When a row began: a call's own start, a comparison's first call. */
const startedOf = (row: Listed): number => (row.kind === "run" ? row.run.started_at : Math.min(...row.runs.map((run) => run.started_at)));

/** The rows under the day each began, newest day first, as Calls and Cases list theirs: Today, Yesterday, then the date. */
function byDay(rows: readonly Listed[]): { name: string; rows: Listed[] }[] {
  const today = utcDay(Date.now() / 1000);
  const yesterday = utcDay(Date.now() / 1000 - 86400);
  const days = new Map<string, Listed[]>();
  for (const row of rows) {
    const day = utcDay(startedOf(row));
    days.set(day, [...(days.get(day) ?? []), row]);
  }
  return [...days].map(([day, held]) => ({ name: day === today ? "Today" : day === yesterday ? "Yesterday" : dayLabel(day), rows: held }));
}

/** What a row wears: who called, as its title names them, and over their corner the agent they rang; the agent alone for a call that names nobody. A comparison of several tasks wears its first caller. */
function CallerMark({ run }: { run: PersonaRun }): ReactNode {
  if (run.persona === null || run.persona === undefined) return <AvatarOf name={run.agent} size={28} />;
  return (
    <span className="sim-pair" title={`${run.persona} rang ${run.agent}`}>
      <PersonaAvatar name={run.persona} size={28} />
      <span className="sim-pair-agent">
        <AvatarOf name={run.agent} size={16} />
      </span>
    </span>
  );
}

function RunRow({ run }: { run: PersonaRun }): ReactNode {
  const standing = standingOf(run);
  const under = standing === "live" ? "on the line now" : [ago(run.started_at), lengthOf(run.started_at, run.ended_at), run.score !== null && run.score.judged > 0 ? `${run.score.held}/${run.score.judged} held` : null].filter((part) => part !== null).join(" · ");
  return (
    <NavLink to={`${HOME}/${run.call}`} className={rowClass}>
      <CallerMark run={run} />
      <span className="app-row-words">
        <span className="app-row-top">
          <span className="dash-clip">{run.persona ?? "A caller"}</span>
          <span className={DOTS[standing]} title={SAID[standing]} aria-hidden="true" />
        </span>
        <span className="app-row-under dash-clip">
          {run.agent} · {under}
        </span>
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
      {first !== undefined && <CallerMark run={first} />}
      <span className="app-row-words">
        <span className="app-row-top">
          <span className="dash-clip">
            {models} models, {tasks} {tasks === 1 ? "task" : "tasks"}
          </span>
          {live ? <span className={DOTS.live} title={SAID.live} aria-hidden="true" /> : <span className="dash-tag">Compared</span>}
        </span>
        <span className="app-row-under dash-clip">
          {first?.agent} · {live ? "on the line now" : ago(first?.started_at ?? null)}
        </span>
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
      {results && <ResultsPanel watched={watched} run={run} onClose={() => setResults(false)} />}
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
    <aside className="app-list" aria-label={LISTED}>
      <div className="app-list-head">
        <span className="app-list-title">{LISTED}</span>
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
        {byDay(listed(runs ?? [])).map((day) => (
          <div key={day.name} className="sim-day-group">
            <div className="sim-day">{day.name}</div>
            {day.rows.map((row) => (row.kind === "run" ? <RunRow key={row.run.call} run={row.run} /> : <ComparisonRow key={row.id} id={row.id} runs={row.runs} />))}
          </div>
        ))}
        {runs !== null && runs.length === 0 && <p className="dash-quiet app-none">{CHECKING ? "No check call yet. The first one shows up here." : "No simulation yet. The first one shows up here."}</p>}
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
            <>
              {!agentsRead ? (
                <p className="dash-quiet app-open-note">Reading…</p>
              ) : CHECKING ? (
                <CheckCall agents={agents} asked={params.get("agent")} askedCaller={params.get("persona")} typical={typical} onStarted={(calls) => void started(calls)} />
              ) : (
                <Composer agents={agents} asked={params.get("agent")} askedCaller={params.get("persona")} typical={typical} onStarted={(calls) => void started(calls)} onCompared={(id) => void compared(id)} />
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
