/** A comparison's board: the setups ranked by the tasks each got done, how often, how fast and for how much; and under them every task against every setup, each run its call. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { cellOf, qualityOf, readComparison, replyOf, setupKey, setupName, setupUnder, THE_GOAL, type AgentValues, type Cell, type Comparison, type ComparisonRow } from "./door";

// The board is read again this often while a call of it waits, is on the line or is being judged.
const ASKED_EVERY_MS = 4000;

const WAITING: readonly Cell[] = ["live", "scoring"];
const RUN_SAID: Record<Cell, string> = { live: "On the line", scoring: "Being judged", passed: "Done", failed: "Failed", unjudged: "Not judged", unstarted: "Did not start" };

/** One setup of the comparison, with what its calls add up to. */
interface Standing {
  key: string;
  against: AgentValues;
  rows: ComparisonRow[];
  /** Its runs that did their task, of the ones that were judged on it. */
  done: number;
  judged: number;
  /** The tasks it did every time it was put to them, of the tasks in the comparison. */
  always: number;
  /** The share of the other judges' verdicts that held, over its calls: how well, apart from whether. */
  quality: number | null;
  reply: number | null;
  slowest: number | null;
  /** The agent's replies the callers talked over, of all it gave. */
  cut: number;
  replies: number;
  cost: number | null;
  /** Over its spoken calls that were measured: the replies the room cut off and the turns nobody said, the lines never answered of those said, and the words heard wrong. */
  heard: { faults: number; unanswered: number; lines: number; wrong: number | null } | null;
}

function middle(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const half = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? (sorted[half] ?? null) : ((sorted[half - 1] ?? 0) + (sorted[half] ?? 0)) / 2;
}

/** The setups in the order asked, each with its rows; one made before plans were kept is what its rows say. */
function columns(read: Comparison): { key: string; against: AgentValues; rows: ComparisonRow[] }[] {
  const asked = read.against.length > 0 ? read.against : [...new Map(read.rows.map((row) => [setupKey(row.against), row.against])).values()];
  return asked.map((against) => ({ key: setupKey(against), against, rows: read.rows.filter((row) => setupKey(row.against) === setupKey(against)) }));
}

function standings(read: Comparison): Standing[] {
  const all = columns(read).map(({ key, against, rows }) => {
    const cells = rows.map((row) => cellOf(row));
    const quality = rows.map(qualityOf);
    const verdicts = quality.reduce((sum, one) => sum + one.judged, 0);
    const slowest = rows.flatMap((row) => row.slowest_reply ?? []);
    const costs = rows.flatMap((row) => row.cost_usd ?? []);
    const hearings = rows.flatMap((row) => row.hearing ?? []);
    const always = read.personas.filter((task) => {
      const runs = rows.filter((row) => row.persona === task).map((row) => cellOf(row));
      return runs.length > 0 && runs.every((cell) => cell === "passed");
    }).length;
    return {
      key,
      against,
      rows,
      done: cells.filter((cell) => cell === "passed").length,
      judged: cells.filter((cell) => cell === "passed" || cell === "failed").length,
      always,
      quality: verdicts === 0 ? null : quality.reduce((sum, one) => sum + one.held, 0) / verdicts,
      reply: middle(rows.flatMap((row) => replyOf(row) ?? [])),
      slowest: slowest.length === 0 ? null : Math.max(...slowest),
      cut: rows.reduce((sum, row) => sum + row.cut_off, 0),
      replies: rows.reduce((sum, row) => sum + row.replies, 0),
      cost: costs.length === 0 ? null : costs.reduce((sum, cost) => sum + cost, 0) / costs.length,
      heard:
        hearings.length === 0
          ? null
          : {
              faults: hearings.reduce((sum, one) => sum + one.cut_by_the_room + one.phantom_turns, 0),
              unanswered: hearings.reduce((sum, one) => sum + one.unanswered, 0),
              lines: hearings.reduce((sum, one) => sum + one.lines, 0),
              wrong: middle(hearings.flatMap((one) => one.word_error_rate ?? [])),
            },
    };
  });
  const share = (one: Standing): number => (one.judged === 0 ? 0 : one.done / one.judged);
  // The best is the one a person would pick: the most of its runs done, then the best quality, then the fastest reply, then the cheapest.
  return all.sort((one, other) => share(other) - share(one) || other.done - one.done || (other.quality ?? 0) - (one.quality ?? 0) || (one.reply ?? Infinity) - (other.reply ?? Infinity) || (one.cost ?? Infinity) - (other.cost ?? Infinity));
}

function replied(seconds: number | null): string {
  if (seconds === null) return "—";
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(1)} s`;
}

function cost(usd: number | null): string {
  return usd === null ? "—" : `$${usd.toFixed(usd < 0.1 ? 3 : 2)}`;
}

/** What each judge said of a run, the goal's first: read without opening the call. */
function verdictsOf(row: ComparisonRow): string {
  const said = [...row.judges].sort((one, other) => Number(other.name === THE_GOAL) - Number(one.name === THE_GOAL)).map((judge) => `${judge.verdict === "held" ? "✓" : judge.verdict === "broken" ? "✗" : "·"} ${judge.name}: ${judge.reason}`);
  return [RUN_SAID[cellOf(row)], row.why, ...said].filter((part) => part !== null && part !== "").join("\n\n");
}

/** One task under one setup: each run a dot that opens its call, and what the runs add up to. */
function CellView({ rows, asked, waiting }: { rows: ComparisonRow[]; asked: number; waiting: boolean }): ReactNode {
  const cells = rows.map((row) => cellOf(row));
  const done = cells.filter((cell) => cell === "passed").length;
  const judged = cells.filter((cell) => cell === "passed" || cell === "failed").length;
  const going = cells.some((cell) => WAITING.includes(cell));
  const unplaced = Math.max(0, asked - rows.length);
  const tone = going || (waiting && unplaced > 0) ? "live" : judged === 0 ? (rows.length === 0 ? "none" : "unjudged") : done === judged ? "passed" : done === 0 ? "failed" : "mixed";
  const said = tone === "live" ? (rows.length === 0 ? "Waiting its turn" : "Running") : tone === "none" ? "Not placed" : tone === "unjudged" ? RUN_SAID[cells[0] ?? "unjudged"] : asked === 1 ? (done === 1 ? "Done" : "Failed") : `${done} of ${judged} done`;
  const quality = rows.map(qualityOf).reduce((sum, one) => ({ held: sum.held + one.held, judged: sum.judged + one.judged }), { held: 0, judged: 0 });
  const under = judged === 0 ? null : [quality.judged === 0 ? null : `quality ${quality.held}/${quality.judged}`, replied(middle(rows.flatMap((row) => replyOf(row) ?? []))), cost(middle(rows.flatMap((row) => row.cost_usd ?? [])))].filter((part) => part !== null).join(" · ");
  return (
    <div className={`cmp-cell cmp-cell-${tone}`}>
      <span className="cmp-cell-said">{said}</span>
      {under !== null && <span className="cmp-cell-under">{under}</span>}
      <span className="cmp-runs">
        {rows.map((row, at) => (
          <Link key={row.call} to={`/simulations/${row.call}`} className={`cmp-run cmp-run-${cellOf(row)}`} title={verdictsOf(row)} aria-label={`Run ${at + 1}: ${RUN_SAID[cellOf(row)]}`} />
        ))}
        {Array.from({ length: unplaced }, (_, at) => (
          <span key={`unplaced-${at}`} className={waiting ? "cmp-run cmp-run-waiting" : "cmp-run cmp-run-none"} title={waiting ? "Waiting for a place on the line" : "Never placed"} />
        ))}
      </span>
    </div>
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
        const placing = answered.waiting > 0 && !answered.abandoned;
        if (placing || answered.rows.some((row) => WAITING.includes(cellOf(row)))) timer = window.setTimeout(() => void ask(), ASKED_EVERY_MS);
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

  const ranked = standings(read);
  const tasks = read.personas;
  const placing = read.waiting > 0 && !read.abandoned;
  const going = placing || read.rows.some((row) => WAITING.includes(cellOf(row)));
  const best = !going && (ranked[0]?.judged ?? 0) > 0 ? ranked[0]?.key : undefined;
  const fastest = Math.min(...ranked.flatMap((one) => one.reply ?? []));
  const cheapest = Math.min(...ranked.flatMap((one) => one.cost ?? []));
  const planned = read.planned > 0 ? read.planned : read.rows.length;
  const ended = read.rows.filter((row) => !WAITING.includes(cellOf(row))).length;
  const repeated = read.repeats > 1;

  return (
    <div className="cmp">
      <header className="cmp-head">
        <h2 className="app-name">
          {ranked.length} {ranked.length === 1 ? "setup" : "setups"} on {tasks.length} {tasks.length === 1 ? "task" : "tasks"}
          {repeated && `, ${read.repeats} times each`}
        </h2>
        <p className="dash-quiet">
          {read.agent} · {read.voice ? "spoken" : "typed"} · a task is done when its caller got what it expected; quality is the other judges
        </p>
      </header>
      {refused !== null && <p className="app-refused">{refused}</p>}
      {going && (
        <div className="cmp-progress" role="status">
          <span className="cmp-progress-track">
            <span style={{ width: `${planned === 0 ? 0 : (ended / planned) * 100}%` }} />
          </span>
          <span className="dash-quiet">
            {ended} of {planned} calls finished{read.waiting > 0 ? ` · ${read.waiting} waiting their turn` : ""}
          </span>
        </div>
      )}
      {read.abandoned && <p className="app-refused">{read.waiting} calls were never placed: the gateway placing them was restarted. Run the comparison again for those.</p>}
      {read.refused.length > 0 && (
        <details className="cmp-refused">
          <summary>
            {read.refused.length} {read.refused.length === 1 ? "call was" : "calls were"} refused
          </summary>
          <ul>
            {[...new Set(read.refused.map((one) => `${one.persona} on ${setupName(one.against)}: ${one.why}`))].map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </details>
      )}

      <div className="cmp-ranks">
        {ranked.map((one, at) => (
          <section key={one.key} className={one.key === best ? "dash-card cmp-rank cmp-rank-best" : "dash-card cmp-rank"} aria-label={setupName(one.against)}>
            <div className="cmp-rank-top">
              <span className="cmp-place">{at + 1}</span>
              <span className="cmp-rank-words">
                <span className="cmp-rank-name dash-clip">{setupName(one.against)}</span>
                {setupUnder(one.against) !== "" && <span className="cmp-rank-under dash-clip">{setupUnder(one.against)}</span>}
              </span>
              {one.key === best && <span className="ui-badge">Best</span>}
            </div>
            <div className="cmp-done">
              <b>{repeated ? (one.judged === 0 ? "—" : `${Math.round((one.done / one.judged) * 100)}%`) : one.done}</b>
              <span>{repeated ? `of runs done · ${one.always} of ${tasks.length} tasks every time` : `of ${tasks.length} ${tasks.length === 1 ? "task" : "tasks"} done`}</span>
            </div>
            <div className="cmp-pips" aria-hidden>
              {tasks.map((task) => {
                const runs = one.rows.filter((mine) => mine.persona === task).map((row) => cellOf(row));
                const tone = runs.length === 0 ? "none" : runs.some((cell) => WAITING.includes(cell)) ? "live" : runs.every((cell) => cell === "passed") ? "passed" : runs.some((cell) => cell === "passed") ? "mixed" : runs.some((cell) => cell === "failed" || cell === "unstarted") ? "failed" : "none";
                return <span key={task} className={`cmp-pip cmp-pip-${tone}`} />;
              })}
            </div>
            <dl className="cmp-facts">
              <div>
                <dt>{read.voice ? "Typical reply" : "First token"}</dt>
                <dd className={one.reply !== null && one.reply === fastest && ranked.length > 1 ? "cmp-top" : ""}>{replied(one.reply)}</dd>
              </div>
              <div>
                <dt>Slowest reply</dt>
                <dd>{replied(one.slowest)}</dd>
              </div>
              <div>
                <dt>Cost a call</dt>
                <dd className={one.cost !== null && one.cost === cheapest && ranked.length > 1 ? "cmp-top" : ""}>{cost(one.cost)}</dd>
              </div>
              <div>
                <dt>Quality</dt>
                <dd title="The other judges that held, apart from the task itself">{one.quality === null ? "—" : `${Math.round(one.quality * 100)}%`}</dd>
              </div>
              <div>
                <dt>Cut off</dt>
                <dd title="The agent's replies a caller talked over">{one.replies === 0 ? "—" : `${one.cut} of ${one.replies}`}</dd>
              </div>
              {one.heard !== null && (
                <>
                  <div>
                    <dt>Not answered</dt>
                    <dd className={one.heard.unanswered > 0 ? "cmp-low" : ""} title="The caller's lines the agent said nothing to">
                      {one.heard.unanswered} of {one.heard.lines}
                    </dd>
                  </div>
                  <div>
                    <dt>Heard the room</dt>
                    <dd className={one.heard.faults > 0 ? "cmp-low" : ""} title="Replies cut off with nobody speaking, and turns heard that nobody said">
                      {one.heard.faults}
                    </dd>
                  </div>
                  <div>
                    <dt>Words wrong</dt>
                    <dd className={one.heard.wrong !== null && one.heard.wrong > 0.15 ? "cmp-low" : ""} title="Word error rate against what the callers really said">
                      {one.heard.wrong === null ? "—" : `${Math.round(Math.min(one.heard.wrong, 9.99) * 100)}%`}
                    </dd>
                  </div>
                </>
              )}
            </dl>
          </section>
        ))}
      </div>

      <section className="dash-card cmp-matrix" aria-label="Every task against every setup">
        <div className="cmp-grid" style={{ gridTemplateColumns: `minmax(140px, 1.1fr) repeat(${ranked.length}, minmax(160px, 1fr))` }}>
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
                <CellView key={one.key} rows={one.rows.filter((mine) => mine.persona === task)} asked={read.repeats} waiting={placing} />
              ))}
            </div>
          ))}
        </div>
        <p className="dash-quiet cmp-foot">Each dot is one run: open it to read its call and what each judge said.</p>
      </section>
    </div>
  );
}
