/** One run, golden by golden: each cell where it broke, and open, its transcript with every step's state. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { dayAndTime } from "../../lib/format";
import { Card, CardHead, Empty, KV, Pill } from "../../ui";
import { deltaBetween } from "./deltas";
import type { Cell, EvalRun } from "./door";
import { brokeAt, readGolden, readScores } from "./golden-words";
import { Reproductions } from "./reproductions";
import { Changed } from "./run-table";
import type { Listed } from "./testing";
import { StateMark, Transcript } from "./transcript";

const STATUS_TONE = { done: "green", running: "amber", failed: "red" } as const;

const COLUMNS = "minmax(0,1fr) minmax(0,.7fr) minmax(0,1.2fr) 84px";

/** `goldens` are the ones the agent's directory lists: a cell of one of them reads with its lines; any other, from its metrics alone. */
export function RunDetail({ run, before, goldens }: { run: EvalRun; before: EvalRun | undefined; goldens: readonly Listed[] }): ReactNode {
  const cells = run.matrix?.runs ?? [];
  // What broke is what a person opens a run for: those cells start open.
  const [open, setOpen] = useState<Set<string>>(() => new Set(cells.filter((cell) => !heldAll(cell)).map(keyOf)));
  const flip = (key: string): void => {
    const next = new Set(open);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setOpen(next);
  };
  return (
    <Card>
      <CardHead title={run.id} meta={`${run.agent} · ${String(run.matrix?.judge_calls ?? 0)} judge calls`}>
        <span className="ev-head-end">
          <Pill tone={STATUS_TONE[run.status]}>{run.status}</Pill>
        </span>
      </CardHead>
      <div className="ev-facts">
        <KV label="Started">{dayAndTime(run.started_at)}</KV>
        <KV label="Finished">{dayAndTime(run.finished_at)}</KV>
        {run.error !== null && <KV label="Error">{run.error}</KV>}
        <KV label="Since before">
          <Changed delta={deltaBetween(run, before)} />
        </KV>
      </div>

      {run.matrix === null ? (
        <Empty>No verdict yet.</Empty>
      ) : (
        cells.map((cell) => {
          const key = keyOf(cell);
          const golden = goldens.find((one) => one.name === cell.golden);
          const read = golden === undefined ? readScores(cell.scores) : readGolden(golden, cell.scores);
          const held = heldAll(cell);
          const opened = run.calls.find((call) => call.golden === cell.golden && call.model === cell.model);
          return (
            <div key={key} className={open.has(key) ? "ev-golden ev-golden-open" : "ev-golden"}>
              <div className="ui-table-row ui-table-row-link" style={{ gridTemplateColumns: COLUMNS }} onClick={() => flip(key)}>
                <span className="ev-golden-words">
                  <span className="ev-golden-name ui-clip">{cell.golden}</span>
                  {opened !== undefined && (
                    <Link className="ev-golden-call ui-clip" to={`/calls/${opened.call}`} onClick={(event) => event.stopPropagation()}>
                      {opened.call}
                    </Link>
                  )}
                </span>
                <span className="ui-cell-faint ui-clip">{cell.model}</span>
                <span className="ev-golden-where ui-clip">{held ? "" : `broke at ${brokeAt(read) ?? "a check"}`}</span>
                <span className="ui-cell-end">
                  <StateMark state={held ? "held" : "broke"} />
                </span>
              </div>
              {open.has(key) && <Transcript read={read} />}
            </div>
          );
        })
      )}

      <Reproductions run={run.id} />
    </Card>
  );
}

function heldAll(cell: Cell): boolean {
  return cell.scores.every((score) => score.passed);
}

function keyOf(cell: Cell): string {
  return `${cell.golden}/${cell.model}`;
}
