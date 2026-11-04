/** A comparison's table: the same persona against the agent under each configuration, best first, each row opening its call. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { duration, usd } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import { Pill, TableHead, TableRow } from "../../ui";
import { readComparison, said, type Comparison, type ComparisonRow } from "./comparing";

// Read again while a call is on the line, and for a while after it ended: the judges answer after the hang-up.
const READ_EVERY_MS = 3000;
const JUDGED_WITHIN_S = 120;
const COLUMNS = "28px minmax(0, 1fr) 150px 84px 84px 84px 84px 70px 64px";
const LABELS = ["#", "The agent runs on", "Judges", "Reply>", "Thinks>", "Speaks>", "Hears>", "Cost>", "Length>"] as const;

/** Seconds as the table says them: 1.24 s, 480 ms; an empty cell for a measure no turn took. */
function seconds(value: number | null): string {
  if (value === null) return "";
  return value >= 1 ? `${value.toFixed(2)} s` : `${String(Math.round(value * 1000))} ms`;
}

function unsettled(row: ComparisonRow, now: number): boolean {
  return row.ended_at === null || (row.score === null && now - row.ended_at < JUDGED_WITHIN_S);
}

export function ComparisonTable({ inView, comparison }: { inView: string; comparison: string }): ReactNode {
  const credentials = useCredentials();
  const [read, setRead] = useState<Comparison | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    let timer: number | undefined;
    const again = async (): Promise<void> => {
      try {
        const found = await readComparison(credentials, comparison);
        if (gone) return;
        setRead(found);
        setRefused(null);
        if (found.rows.some((row) => unsettled(row, Date.now() / 1000))) timer = window.setTimeout(() => void again(), READ_EVERY_MS);
      } catch (failed) {
        if (gone) return;
        setRefused(saidBy(failed));
        timer = window.setTimeout(() => void again(), READ_EVERY_MS);
      }
    };
    void again();
    return () => {
      gone = true;
      window.clearTimeout(timer);
    };
  }, [credentials, comparison]);

  const base = rowAt(inView, "simulations");
  const live = read?.rows.filter((row) => row.ended_at === null).length ?? 0;
  return (
    <section className="sims-cmp" aria-label="comparison">
      <div className="runs-head">
        <span className="runs-title">Comparison</span>
        <span className="runs-meta">
          {read === null ? (refused ?? "reading…") : [`${read.persona} against ${read.agent}`, `${String(read.rows.length)} ${read.rows.length === 1 ? "call" : "calls"}`, live === 0 ? "best first" : `${String(live)} on a call`].join(" · ")}
        </span>
        <Link className="sim-link" to={base}>
          Every simulation
        </Link>
      </div>
      {read !== null && (
        <div className="sims-cmp-table">
          <TableHead columns={COLUMNS} labels={LABELS} />
          {read.rows.map((row, index) => (
            <TableRow key={row.call} columns={COLUMNS} to={`${base}/${row.call}${read.voice ? "?spoken=1" : ""}`}>
              <span className="sims-cmp-n">{String(index + 1)}</span>
              <span className="sims-cmp-said">{said(row.against)}</span>
              <Judges row={row} />
              <span className="sims-cmp-num">{seconds(row.latency.e2e_latency)}</span>
              <span className="sims-cmp-num">{seconds(row.latency.llm_node_ttft)}</span>
              <span className="sims-cmp-num">{seconds(row.latency.tts_node_ttfb)}</span>
              <span className="sims-cmp-num">{seconds(row.latency.transcription_delay)}</span>
              <span className="sims-cmp-num">{row.cost_usd === null ? "" : usd(row.cost_usd)}</span>
              <span className="sims-cmp-num">{row.ended_at === null ? "" : duration(row)}</span>
            </TableRow>
          ))}
        </div>
      )}
      {refused !== null && read !== null && <p className="sim-note sim-refused">{refused}</p>}
    </section>
  );
}

// What the judges answered: held of judged, or that the call is still on the line or was never scored.
function Judges({ row }: { row: ComparisonRow }): ReactNode {
  if (row.ended_at === null) {
    return (
      <Pill tone="green" small>
        on a call
      </Pill>
    );
  }
  if (row.score === null) return <span className="runs-unjudged">{row.end_reason === null ? "not judged" : row.end_reason.replace(/_/g, " ")}</span>;
  const tone = row.score.passed ? "green" : "red";
  return (
    <span className={`runs-verdict-said runs-tone-${tone}`}>
      {row.score.passed ? "held" : "broke"} {String(row.score.held)}/{String(row.score.judged)}
    </span>
  );
}
