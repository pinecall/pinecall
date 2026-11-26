/** A comparison's board, which is its benchmark: the setups held to two bars and ranked, every task against every setup with each run its call, and under them the judges, the rounds, what failed and what does not count. */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { nameOf, rowsOf, type Bars, type Setup } from "@pinecall/agents/evals";
import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { benchmarkOf, readAllHeard, type Heard } from "./benchmark";
import { TheBars, UnderTheBoard } from "./benchmark-sections";
import { cellOf, countedOf, qualityOf, readComparison, replyOf, setupKey, setupName, setupUnder, THE_GOAL, type Cell, type Comparison, type ComparisonRow } from "./door";

/** Several comparisons read as one are named together in the address, a plus between them. */
export const TOGETHER = "+";

// The board is read again this often while a call of it waits, is on the line or is being judged.
const ASKED_EVERY_MS = 4000;

const WAITING: readonly Cell[] = ["live", "scoring"];
const RUN_SAID: Record<Cell, string> = { live: "On the line", scoring: "Being judged", passed: "Done", failed: "Failed", unjudged: "Not judged", unstarted: "Did not start", uncounted: "Not counted" };

function middle(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const half = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? (sorted[half] ?? null) : ((sorted[half - 1] ?? 0) + (sorted[half] ?? 0)) / 2;
}

// Several comparisons are one table, as `pinecall benchmark a b` reads them: a caller rung again under
// the same setup is another round of it. What is still being placed is summed.
/** The comparisons named, as the one the board draws. */
function together(tables: readonly Comparison[]): Comparison {
  const first = tables[0] as Comparison;
  if (tables.length === 1) return first;
  const against = [...new Map(tables.flatMap((table) => table.against).map((one) => [setupKey(one), one])).values()];
  return {
    ...first,
    personas: [...new Set(tables.flatMap((table) => table.personas))],
    against,
    rows: rowsOf(tables),
    // Each comparison rang its own setups its own times: a cell is owed what the one that asked most asked.
    repeats: Math.max(...tables.map((table) => table.repeats)),
    planned: tables.reduce((sum, table) => sum + table.planned, 0),
    waiting: tables.reduce((sum, table) => sum + table.waiting, 0),
    playing: tables.some((table) => table.playing),
    abandoned: tables.some((table) => table.abandoned),
    stopped: tables.flatMap((table) => table.stopped),
    refused: tables.flatMap((table) => table.refused),
  };
}

/** What the board adds to a setup's benchmark numbers, from its rows: the other judges' share that held, and the replies a caller talked over. */
function besides(rows: readonly ComparisonRow[]): { quality: number | null; cut: number; replies: number } {
  const counted = countedOf(rows);
  const quality = counted.map(qualityOf);
  const verdicts = quality.reduce((sum, one) => sum + one.judged, 0);
  return {
    quality: verdicts === 0 ? null : quality.reduce((sum, one) => sum + one.held, 0) / verdicts,
    cut: counted.reduce((sum, row) => sum + row.cut_off, 0),
    replies: counted.reduce((sum, row) => sum + row.replies, 0),
  };
}

const percent = (share: number | null): string => (share === null ? "—" : `${Math.round(share * 100)}%`);

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
  return [RUN_SAID[cellOf(row)], row.invalid?.why ?? null, row.why, ...said].filter((part) => part !== null && part !== "").join("\n\n");
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
  const counted = countedOf(rows);
  const quality = counted.map(qualityOf).reduce((sum, one) => ({ held: sum.held + one.held, judged: sum.judged + one.judged }), { held: 0, judged: 0 });
  const uncounted = rows.length - counted.length;
  const under = judged === 0 ? null : [quality.judged === 0 ? null : `quality ${quality.held}/${quality.judged}`, replied(middle(counted.flatMap((row) => replyOf(row) ?? []))), cost(middle(counted.flatMap((row) => row.cost_usd ?? []))), uncounted === 0 ? null : `${uncounted} not counted`].filter((part) => part !== null).join(" · ");
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

/** Another comparison of the same agent, as the board offers it to be read with the one open. */
export interface Alongside {
  id: string;
  said: string;
}

export function Board({ comparison, bars, onBars, alongside, onTogether }: { comparison: string; bars: Bars; onBars: (bars: Bars) => void; alongside: readonly Alongside[]; onTogether: (ids: string[]) => void }): ReactNode {
  const credentials = useCredentials();
  const [tables, setTables] = useState<Comparison[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [heard, setHeard] = useState<ReadonlyMap<string, Heard>>(new Map());

  useEffect(() => {
    let gone = false;
    let timer: number | undefined;
    const ask = async (): Promise<void> => {
      try {
        const answered = await Promise.all(comparison.split(TOGETHER).map((id) => readComparison(credentials, id)));
        if (gone) return;
        setTables(answered);
        setRefused(null);
        const placing = answered.some((one) => (one.waiting > 0 || one.playing) && !one.abandoned);
        if (placing || answered.some((one) => one.rows.some((row) => WAITING.includes(cellOf(row))))) timer = window.setTimeout(() => void ask(), ASKED_EVERY_MS);
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

  const read = useMemo(() => (tables === null ? null : together(tables)), [tables]);
  const placing = read !== null && (read.waiting > 0 || read.playing) && !read.abandoned;
  const going = read !== null && (placing || read.rows.some((row) => WAITING.includes(cellOf(row))));
  // Each call's own replies are in its log: read once the calls are over, for the reply nine in ten are under.
  const over = read === null || going ? "" : read.rows.flatMap((row) => (row.ended_at === null ? [] : [`${row.call} ${row.started_at}`])).join("\n");
  useEffect(() => {
    if (over === "") return;
    let gone = false;
    const rows = over.split("\n").map((line) => ({ call: line.split(" ")[0] ?? "", started_at: Number(line.split(" ")[1]) }));
    void readAllHeard(credentials, rows).then((found) => {
      if (!gone) setHeard(found);
    });
    return () => {
      gone = true;
    };
  }, [credentials, over]);
  const made = useMemo(() => (tables === null ? null : benchmarkOf(tables, bars, heard)), [tables, bars, heard]);

  if (read === null || made === null) return <p className={refused === null ? "dash-quiet" : "app-refused"}>{refused ?? "Reading the comparison…"}</p>;

  const ranked = made.setups;
  const rowsUnder = (one: Setup): ComparisonRow[] => read.rows.filter((row) => nameOf(row.against) === one.name);
  const tasks = read.personas;
  const best = going ? null : made.verdict.winner;
  // A typed call has no spoken reply: its setups are told apart by the model's first token.
  const replyOn = (one: Setup): number | null => (read.voice ? one.reply.p50 : one.stages.llm_ttft);
  const fastest = Math.min(...ranked.flatMap((one) => replyOn(one) ?? []));
  // A setup with a model nobody priced has no cost to be the cheapest by.
  const cheapest = Math.min(...ranked.flatMap((one) => (one.cost.unpriced.length > 0 ? [] : (one.cost.per_completed ?? []))));
  const planned = read.planned > 0 ? read.planned : read.rows.length;
  // A call that did not count stands for none of the calls planned: the one placed in its stead does.
  const ended = read.rows.filter((row) => row.valid && !WAITING.includes(cellOf(row))).length;
  const repeated = read.repeats > 1;
  const open = comparison.split(TOGETHER);
  const several = open.length > 1;

  return (
    <div className="cmp">
      <header className="cmp-head">
        <h2 className="app-name">
          {ranked.length} {ranked.length === 1 ? "setup" : "setups"} on {tasks.length} {tasks.length === 1 ? "task" : "tasks"}
          {repeated && !several && `, ${read.repeats} times each`}
          {several && ` · ${open.length} comparisons read as one`}
        </h2>
        <p className="dash-quiet">
          {read.agent} · {read.voice ? "spoken" : "typed"} · a task is done when its caller got what it expected; quality is the other judges
        </p>
      </header>
      {alongside.length > 1 && (
        <div className="cmp-with" role="group" aria-label="Read as one table with">
          <span className="dash-quiet">One table of</span>
          {alongside.map((one) => {
            const on = open.includes(one.id);
            return (
              <button key={one.id} type="button" role="checkbox" aria-checked={on} disabled={on && !several} className={on ? "app-button cmp-with-on" : "app-button"} onClick={() => onTogether(on ? open.filter((id) => id !== one.id) : [...open, one.id])}>
                {one.said}
              </button>
            );
          })}
        </div>
      )}
      {refused !== null && <p className="app-refused">{refused}</p>}
      <TheBars tables={tables ?? []} made={made} bars={bars} onBars={onBars} going={going} />
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
      {read.stopped.map((one) => (
        <p key={setupName(one.against)} className="app-refused">
          No more calls are placed on {setupName(one.against)}: {one.why}
        </p>
      ))}
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
        {ranked.map((one, at) => {
          const rows = rowsUnder(one);
          const beside = besides(rows);
          const reply = replyOn(one);
          const always = one.by_caller.filter((task) => task.every).length;
          return (
            <section key={one.name} className={one.name === best ? "dash-card cmp-rank cmp-rank-best" : "dash-card cmp-rank"} aria-label={setupName(one.values)}>
              <div className="cmp-rank-top">
                <span className="cmp-place">{at + 1}</span>
                <span className="cmp-rank-words">
                  <span className="cmp-rank-name dash-clip">{setupName(one.values)}</span>
                  {setupUnder(one.values) !== "" && <span className="cmp-rank-under dash-clip">{setupUnder(one.values)}</span>}
                </span>
                {one.name === best && <span className="ui-badge">{ranked.length === 1 ? "Clears both bars" : "The one to take"}</span>}
                {one.thin && <span className="ui-badge ui-badge-quiet">Most calls not counted</span>}
              </div>
              <div className="cmp-done">
                <b className={one.thin || one.clears.floor === null ? "" : one.clears.floor ? "cmp-top" : "cmp-low"}>{percent(one.completed.share)}</b>
                {one.completed.of === 0 ? (
                  <span>None of its calls was judged</span>
                ) : (
                  <span>
                    {one.completed.completed} of {one.completed.of} calls completed
                    {one.completed.low !== null && one.completed.high !== null && ` · plausibly ${percent(one.completed.low)}–${percent(one.completed.high)}`}
                    {repeated && ` · ${always} of ${tasks.length} tasks every time`}
                  </span>
                )}
              </div>
              <div className="cmp-pips" aria-hidden>
                {tasks.map((task) => {
                  const runs = rows.filter((mine) => mine.persona === task).map((row) => cellOf(row));
                  const tone = runs.length === 0 ? "none" : runs.some((cell) => WAITING.includes(cell)) ? "live" : runs.every((cell) => cell === "passed") ? "passed" : runs.some((cell) => cell === "passed") ? "mixed" : runs.some((cell) => cell === "failed" || cell === "unstarted") ? "failed" : "none";
                  return <span key={task} className={`cmp-pip cmp-pip-${tone}`} />;
                })}
              </div>
              <dl className="cmp-facts">
                <div>
                  <dt>{read.voice ? "Typical reply" : "First token"}</dt>
                  <dd className={read.voice && one.clears.ceiling === false ? "cmp-low" : reply !== null && reply === fastest && ranked.length > 1 ? "cmp-top" : ""}>{replied(reply)}</dd>
                </div>
                <div>
                  <dt>Nine in ten under</dt>
                  <dd title="The reply nine in ten of its replies are under, read from each call's log">{replied(one.reply.p90)}</dd>
                </div>
                <div>
                  <dt>Slowest reply</dt>
                  <dd>{replied(one.reply.slowest)}</dd>
                </div>
                <div>
                  <dt>A completed call</dt>
                  <dd className={one.cost.unpriced.length === 0 && one.cost.per_completed !== null && one.cost.per_completed === cheapest && ranked.length > 1 ? "cmp-top" : ""} title={one.cost.unpriced.length > 0 ? `Not priced: ${one.cost.unpriced.join(", ")}` : "Everything its calls cost, over the calls that were completed"}>
                    {one.cost.unpriced.length > 0 && one.cost.total === 0 ? "Not priced" : cost(one.cost.per_completed)}
                    {one.cost.unpriced.length > 0 && one.cost.total > 0 && "*"}
                  </dd>
                </div>
                <div>
                  <dt>Quality</dt>
                  <dd title="The other judges that held, apart from the task itself">{percent(beside.quality)}</dd>
                </div>
                <div>
                  <dt>Cut off</dt>
                  <dd title="The agent's replies a caller talked over">{beside.replies === 0 ? "—" : `${beside.cut} of ${beside.replies}`}</dd>
                </div>
                {one.hearing !== null && (
                  <>
                    <div>
                      <dt>Not answered</dt>
                      <dd className={one.hearing.unanswered > 0 ? "cmp-low" : ""} title="The caller's lines the agent said nothing to">
                        {one.hearing.unanswered} of {one.hearing.lines}
                      </dd>
                    </div>
                    <div>
                      <dt>Heard the room</dt>
                      <dd className={one.hearing.cut_by_the_room + one.hearing.phantom_turns > 0 ? "cmp-low" : ""} title="Replies cut off with nobody speaking, and turns heard that nobody said">
                        {one.hearing.cut_by_the_room + one.hearing.phantom_turns}
                      </dd>
                    </div>
                    <div>
                      <dt>Words wrong</dt>
                      <dd className={one.hearing.word_error_rate !== null && one.hearing.word_error_rate > 0.15 ? "cmp-low" : ""} title="Word error rate against what the callers really said">
                        {one.hearing.word_error_rate === null ? "—" : `${Math.round(Math.min(one.hearing.word_error_rate, 9.99) * 100)}%`}
                      </dd>
                    </div>
                  </>
                )}
              </dl>
            </section>
          );
        })}
      </div>

      <section className="dash-card cmp-matrix" aria-label="Every task against every setup">
        <div className="cmp-grid" style={{ gridTemplateColumns: `minmax(140px, 1.1fr) repeat(${ranked.length}, minmax(160px, 1fr))` }}>
          <span className="cmp-corner dash-quiet">Task</span>
          {ranked.map((one) => (
            <span key={one.name} className="cmp-col dash-clip">
              {setupName(one.values)}
            </span>
          ))}
          {tasks.map((task) => (
            <div key={task} className="cmp-row">
              <span className="cmp-task dash-clip">{task}</span>
              {ranked.map((one) => (
                <CellView key={one.name} rows={rowsUnder(one).filter((mine) => mine.persona === task)} asked={read.repeats} waiting={placing} />
              ))}
            </div>
          ))}
        </div>
        <p className="dash-quiet cmp-foot">Each dot is one run: open it to read its call and what each judge said.</p>
      </section>

      <UnderTheBoard made={made} />
    </div>
  );
}
