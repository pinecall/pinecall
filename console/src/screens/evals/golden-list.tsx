/** The agent's goldens, a row each with where it stands in the newest run; the one open reads as its transcript. */

import type { ReactNode } from "react";

import { Pill } from "../../ui";
import type { EvalRun } from "./door";
import { brokeAt, readGolden, readScores, type Read } from "./golden-words";
import type { Listed } from "./testing";
import { StateMark, Transcript } from "./transcript";

const COLUMNS = "minmax(0,1fr) minmax(0,1fr) 84px";

export function GoldenList({
  names,
  goldens,
  latest,
  open,
  onOpen,
}: {
  names: string[];
  goldens: Listed[];
  /** The newest run with a matrix, whose verdicts the rows show. */
  latest: EvalRun | undefined;
  open: string | null;
  onOpen: (name: string | null) => void;
}): ReactNode {
  return (
    <div className="ev-goldens">
      {names.map((name) => {
        const golden = goldens.find((one) => one.name === name);
        const cells = latest?.matrix?.runs.filter((cell) => cell.golden === name) ?? [];
        // With one model there is one cell to read the turns against; with several, the row says
        // whether every one held and the run's own detail has each.
        const scores = cells.length === 1 ? cells[0]?.scores : undefined;
        const read: Read | null = golden !== undefined ? readGolden(golden, scores) : scores !== undefined ? readScores(scores) : null;
        const held = cells.length === 0 ? undefined : cells.every((cell) => cell.scores.every((score) => score.passed));
        const where = held === false && read !== null && scores !== undefined ? brokeAt(read) : null;
        const isOpen = open === name;
        return (
          <div key={name} className={isOpen ? "ev-golden ev-golden-open" : "ev-golden"}>
            <div className="ui-table-row ui-table-row-link" style={{ gridTemplateColumns: COLUMNS }} onClick={() => onOpen(isOpen ? null : name)}>
              <span className="ev-golden-words">
                <span className="ev-golden-name ui-clip">{name}</span>
                <span className="ev-golden-says ui-clip">{golden === undefined ? "" : firstOf(golden)}</span>
              </span>
              <span className="ev-golden-where ui-clip">{where === null ? (golden === undefined ? "" : turnsOf(golden)) : `broke at ${where}`}</span>
              <span className="ui-cell-end">{held === undefined ? <Pill tone="muted">not run</Pill> : <StateMark state={held ? "held" : "broke"} />}</span>
            </div>
            {isOpen && read !== null && <Transcript read={read} />}
          </div>
        );
      })}
    </div>
  );
}

// What the golden opens with: the caller's first line, or the fact the backend sends first.
function firstOf(golden: Listed): string {
  const first = golden.turns?.[0];
  if (first === undefined) return "";
  if (first.event !== undefined && first.event !== null) return `your backend sends ${first.event.name}`;
  return `“${first.say ?? ""}”`;
}

function turnsOf(golden: Listed): string {
  const count = golden.turns?.length ?? 0;
  return `${String(count)} ${count === 1 ? "turn" : "turns"}`;
}
