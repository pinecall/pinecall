/** A comparison's board: the models ranked by the tasks each got done, how fast it answered and what it cost; and under them every task against every model, each cell its call. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Icon } from "../shell/icons";
import { cellOf, readComparison, replyOf, setupKey, setupName, type AgentValues, type Cell, type Comparison, type ComparisonRow } from "./door";

// The board is read again this often while a call of it is on the line or being judged.
const ASKED_EVERY_MS = 4000;

const WAITING: readonly Cell[] = ["live", "scoring"];
const CELL_SAID: Record<Cell, string> = { live: "On the line", scoring: "Being judged", passed: "Done", failed: "Failed", unjudged: "Not judged", unstarted: "Did not start" };

/** One model of the comparison, with what its calls add up to. */
interface Standing {
  key: string;
  against: AgentValues;
  rows: ComparisonRow[];
  passed: number;
  judged: number;
  /** The share of every judge's verdicts that held, over its judged calls. */
  held: number;
  reply: number | null;
  cost: number | null;
  waiting: boolean;
}

function middle(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const half = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? (sorted[half] ?? null) : ((sorted[half - 1] ?? 0) + (sorted[half] ?? 0)) / 2;
}

function standings(rows: readonly ComparisonRow[]): Standing[] {
  const groups = new Map<string, ComparisonRow[]>();
  for (const row of rows) groups.set(setupKey(row.against), [...(groups.get(setupKey(row.against)) ?? []), row]);
  const all = [...groups.entries()].map(([key, mine]) => {
    const cells = mine.map((row) => cellOf(row));
    const scored = mine.filter((row) => row.score !== null && row.score.judged > 0);
    const verdicts = scored.reduce((sum, row) => sum + (row.score?.judged ?? 0), 0);
    const costs = mine.flatMap((row) => (row.cost_usd === null ? [] : [row.cost_usd]));
    return {
      key,
      against: mine[0]?.against ?? {},
      rows: mine,
      passed: cells.filter((cell) => cell === "passed").length,
      judged: cells.filter((cell) => cell === "passed" || cell === "failed").length,
      held: verdicts === 0 ? 0 : scored.reduce((sum, row) => sum + (row.score?.held ?? 0), 0) / verdicts,
      reply: middle(mine.flatMap((row) => replyOf(row) ?? [])),
      cost: costs.length === 0 ? null : costs.reduce((sum, cost) => sum + cost, 0) / costs.length,
      waiting: cells.some((cell) => WAITING.includes(cell)),
    };
  });
  // The best is the one a person would pick: the most tasks done, then the most verdicts held, then the fastest reply, then the cheapest.
  return all.sort((one, other) => other.passed - one.passed || other.held - one.held || (one.reply ?? Infinity) - (other.reply ?? Infinity) || (one.cost ?? Infinity) - (other.cost ?? Infinity));
}

function replied(seconds: number | null): string {
  if (seconds === null) return "—";
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(1)} s`;
}

function cost(usd: number | null): string {
  return usd === null ? "—" : `$${usd.toFixed(usd < 0.1 ? 3 : 2)}`;
}

function CellView({ row }: { row: ComparisonRow | undefined }): ReactNode {
  if (row === undefined) return <span className="cmp-cell cmp-cell-none">—</span>;
  const cell = cellOf(row);
  const under = cell === "unstarted" ? row.why : cell === "passed" || cell === "failed" ? [row.score === null ? null : `${row.score.held}/${row.score.judged} judges`, replied(replyOf(row)), cost(row.cost_usd)].filter((part) => part !== null).join(" · ") : null;
  return (
    <Link to={`/simulations/${row.call}`} className={`cmp-cell cmp-cell-${cell}`} title={row.score?.reason ?? undefined}>
      <span className="cmp-cell-said">
        {cell === "passed" && <Icon name="check" size={13} />}
        {cell === "failed" && <Icon name="close" size={13} />}
        {CELL_SAID[cell]}
      </span>
      {under !== null && <span className="cmp-cell-under">{under}</span>}
    </Link>
  );
}

export function Board({ comparison }: { comparison: string }): ReactNode {
  const credentials = useCredentials();
  const [read, setRead] = useState<Comparison | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    let timer: number | undefined;
    const ask = async (): Promise<void> => {
      try {
        const answered = await readComparison(credentials, comparison);
        if (gone) return;
        setRead(answered);
        setRefused(null);
        if (answered.rows.some((row) => WAITING.includes(cellOf(row)))) timer = window.setTimeout(() => void ask(), ASKED_EVERY_MS);
      } catch (failed) {
        if (!gone) setRefused(saidBy(failed));
      }
    };
    void ask();
    return () => {
      gone = true;
      window.clearTimeout(timer);
    };
  }, [credentials, comparison]);

  if (read === null) return <p className={refused === null ? "dash-quiet" : "app-refused"}>{refused ?? "Reading the comparison…"}</p>;

  const ranked = standings(read.rows);
  const tasks = read.personas;
  const waiting = ranked.some((one) => one.waiting);
  const best = !waiting && (ranked[0]?.judged ?? 0) > 0 ? ranked[0]?.key : undefined;
  const fastest = Math.min(...ranked.flatMap((one) => one.reply ?? []));
  const cheapest = Math.min(...ranked.flatMap((one) => one.cost ?? []));

  return (
    <div className="cmp">
      <header className="cmp-head">
        <h2 className="app-name">
          {ranked.length} {ranked.length === 1 ? "model" : "models"} on {tasks.length} {tasks.length === 1 ? "task" : "tasks"}
        </h2>
        <p className="dash-quiet">
          {read.agent} · {read.voice ? "spoken" : "typed"} · {waiting ? "calls still on the line: the board fills in as each one is judged" : "a task is done when every judge held on its call, the caller's own expectations among them"}
        </p>
      </header>
      {refused !== null && <p className="app-refused">{refused}</p>}

      <div className="cmp-ranks">
        {ranked.map((one, at) => (
          <section key={one.key} className={one.key === best ? "dash-card cmp-rank cmp-rank-best" : "dash-card cmp-rank"} aria-label={setupName(one.against)}>
            <div className="cmp-rank-top">
              <span className="cmp-place">{at + 1}</span>
              <span className="cmp-rank-name dash-clip">{setupName(one.against)}</span>
              {one.key === best && <span className="ui-badge">Best</span>}
            </div>
            <div className="cmp-done">
              <b>{one.passed}</b>
              <span>
                of {tasks.length} {tasks.length === 1 ? "task" : "tasks"} done
              </span>
            </div>
            <div className="cmp-pips" aria-hidden>
              {tasks.map((task) => {
                const row = one.rows.find((mine) => mine.persona === task);
                return <span key={task} className={`cmp-pip cmp-pip-${row === undefined ? "unjudged" : cellOf(row)}`} />;
              })}
            </div>
            <dl className="cmp-facts">
              <div>
                <dt>{read.voice ? "Typical reply" : "First token"}</dt>
                <dd className={one.reply !== null && one.reply === fastest && ranked.length > 1 ? "cmp-top" : ""}>{replied(one.reply)}</dd>
              </div>
              <div>
                <dt>Cost a call</dt>
                <dd className={one.cost !== null && one.cost === cheapest && ranked.length > 1 ? "cmp-top" : ""}>{cost(one.cost)}</dd>
              </div>
              <div>
                <dt>Judges held</dt>
                <dd>{one.judged === 0 ? "—" : `${Math.round(one.held * 100)}%`}</dd>
              </div>
            </dl>
          </section>
        ))}
      </div>

      <section className="dash-card cmp-matrix" aria-label="Every task against every model">
        <div className="cmp-grid" style={{ gridTemplateColumns: `minmax(140px, 1.1fr) repeat(${ranked.length}, minmax(150px, 1fr))` }}>
          <span className="cmp-corner dash-quiet">Task</span>
          {ranked.map((one) => (
            <span key={one.key} className="cmp-col dash-clip">
              {setupName(one.against)}
            </span>
          ))}
          {tasks.map((task) => (
            <div key={task} className="cmp-row">
              <span className="cmp-task dash-clip">{task}</span>
              {ranked.map((one) => (
                <CellView key={one.key} row={one.rows.find((mine) => mine.persona === task)} />
              ))}
            </div>
          ))}
        </div>
        <p className="dash-quiet cmp-foot">Open a cell to read its call and what each judge said.</p>
      </section>
    </div>
  );
}
