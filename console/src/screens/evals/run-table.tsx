/** Runs table: one row per run, judgments tallied. */

import type { ReactNode } from "react";

import { dayAndTime } from "../../lib/format";
import { Pill, TableHead } from "../../ui";
import { deltaBetween, tallyOf, type Delta } from "./deltas";
import type { EvalRun } from "./door";

const COLUMNS = "minmax(0,1.1fr) 120px 84px 70px 80px minmax(0,1.6fr)";

const STATUS_TONE = { done: "green", running: "amber", failed: "red" } as const;

export function RunTable({ runs, selected, onSelect }: { runs: EvalRun[]; selected: string | null; onSelect: (id: string) => void }): ReactNode {
  return (
    <>
      <TableHead columns={COLUMNS} labels={["Run", "Started", "Status", "Held>", "Judge calls>", "Since the run before"]} />
      {runs.map((run, at) => {
        const tally = tallyOf(run.matrix);
        const open = run.id === selected;
        return (
          <div
            key={run.id}
            className={open ? "ui-table-row ui-table-row-link ev-row-open" : "ui-table-row ui-table-row-link"}
            style={{ gridTemplateColumns: COLUMNS }}
            onClick={() => onSelect(run.id)}
          >
            <span className="ui-cell-link ui-clip">{run.id}</span>
            <span className="ui-cell-faint">{dayAndTime(run.started_at)}</span>
            <span>
              <Pill tone={STATUS_TONE[run.status]}>{run.status}</Pill>
            </span>
            <span className={tally.judgments > 0 && tally.held < tally.judgments ? "ev-num ev-num-bad" : "ev-num"}>
              {tally.judgments === 0 ? "—" : `${tally.held}/${tally.judgments}`}
            </span>
            <span className="ev-num ev-num-faint">{run.matrix?.judge_calls ?? "—"}</span>
            <Changed delta={deltaBetween(run, runs[at + 1])} />
          </div>
        );
      })}
    </>
  );
}

// Lists the judgments that flipped rather than an average, so the reader knows what to open.
export function Changed({ delta }: { delta: Delta | null }): ReactNode {
  if (delta === null) return <span className="ui-cell-faint">first of its kind</span>;
  if (delta.broke.length === 0 && delta.recovered.length === 0) return <span className="ui-cell-faint">±0</span>;
  return (
    <span className="ui-tags">
      {delta.broke.map((name) => (
        <Pill key={`broke-${name}`} tone="red" small>
          broke · {name}
        </Pill>
      ))}
      {delta.recovered.map((name) => (
        <Pill key={`held-${name}`} tone="green" small>
          held again · {name}
        </Pill>
      ))}
    </span>
  );
}
