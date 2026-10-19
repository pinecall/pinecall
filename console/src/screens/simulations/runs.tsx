/** The simulations already run, newest first: who called, when, how it ended and whether the judges held — each row opens its call. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { ago, duration, percent, usd } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import { Button, Chips, Empty, Icon, Pill } from "../../ui";
import type { PersonaRun } from "../personas/door";
import { Face } from "../personas/face";
import type { Runs } from "./use-runs";

type Show = "all" | "broke" | "held" | "running";

const SHOWS: readonly { value: Show; label: string }[] = [
  { value: "all", label: "All" },
  { value: "broke", label: "Broke" },
  { value: "held", label: "Held" },
  { value: "running", label: "On a call" },
];

const shown = (run: PersonaRun, show: Show): boolean => {
  if (show === "running") return run.ended_at === null;
  if (show === "all") return true;
  return run.score !== null && run.score.passed === (show === "held");
};

export function RunsTable({ inView, read }: { inView: string; read: Runs }): ReactNode {
  const [show, setShow] = useState<Show>("all");
  const base = rowAt(inView, "simulations");
  const runs = read.runs ?? [];
  const rows = runs.filter((run) => shown(run, show));
  const judged = runs.filter((run) => run.score !== null);
  const held = judged.filter((run) => run.score?.passed === true).length;
  const cost = runs.reduce((sum, run) => sum + (run.cost_usd ?? 0), 0);
  return (
    <section className="runs">
      <div className="runs-head">
        <span className="runs-title">Runs</span>
        <span className="runs-meta">
          {read.runs === null
            ? "reading…"
            : [`${String(read.total)} in all`, judged.length === 0 ? null : `${percent(held / judged.length)} held`, cost > 0 ? usd(cost) : null].filter((part) => part !== null).join(" · ")}
        </span>
        <span className="runs-chips">
          <Chips options={SHOWS} value={show} onChange={setShow} />
        </span>
      </div>
      {read.runs !== null && read.runs.length === 0 && <Empty>No simulation has run here yet. Tick who calls above and run the first one.</Empty>}
      {rows.length > 0 && (
        <div className="runs-list">
          {rows.map((run) => (
            <Link key={run.call} to={`${base}/${run.call}`} className="runs-row">
              <Face name={run.persona ?? "?"} size={32} />
              <span className="runs-words">
                <span className="runs-name">{run.persona ?? "a caller"}</span>
                <span className="runs-sub">
                  {[ago(run.started_at), inView === "" ? run.agent : null, `${String(run.turns)} turns`, run.ended_at === null ? null : duration(run)].filter((part) => part !== null).join(" · ")}
                </span>
              </span>
              <Verdict run={run} />
              <span className="runs-cost">{run.cost_usd === null || run.cost_usd === undefined ? "" : usd(run.cost_usd)}</span>
              <span className="runs-go" aria-hidden>
                <Icon name="chevron" size={14} />
              </span>
            </Link>
          ))}
        </div>
      )}
      {read.runs !== null && read.runs.length > 0 && rows.length === 0 && <p className="sim-note">None of the runs read is {show === "running" ? "on a call" : show}.</p>}
      {read.runs === null && read.refused === null && <p className="sim-note">Asking the gateway…</p>}
      {read.refused !== null && <p className="sim-note sim-refused">{read.refused}</p>}
      {read.more && (
        <Button size="sm" disabled={read.asking} onClick={read.older}>
          {read.asking ? "Reading…" : `Show more (${String(read.total - (read.runs?.length ?? 0))} older)`}
        </Button>
      )}
    </section>
  );
}

// What the judges answered, as a few words and a bar of how many held. A run nobody judged is not a
// failure: it is a run that was never scored, and says how it ended instead.
function Verdict({ run }: { run: PersonaRun }): ReactNode {
  if (run.ended_at === null) {
    return (
      <Pill tone="green" small>
        on a call
      </Pill>
    );
  }
  if (run.score === null) return <span className="runs-unjudged">{run.end_reason === null ? "not judged" : run.end_reason.replace(/_/g, " ")}</span>;
  const tone = run.score.passed ? "green" : "red";
  return (
    <span className="runs-verdict">
      <span className={`runs-verdict-said runs-tone-${tone}`}>
        {run.score.passed ? "held" : "broke"} {String(run.score.held)}/{String(run.score.judged)}
      </span>
      <span className="runs-bar">
        <span className={`runs-bar-fill runs-fill-${tone}`} style={{ width: `${run.score.judged === 0 ? 0 : (run.score.held / run.score.judged) * 100}%` }} />
      </span>
    </span>
  );
}
