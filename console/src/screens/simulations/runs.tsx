/** The simulations already run, as a table: who called, when, how long, what it cost and how it went — each row opens its call. */

import { useState, type ReactNode } from "react";

import { ago, duration } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import { Button, Chips, Empty, Pill, TableHead, TableRow } from "../../ui";
import type { PersonaRun } from "../personas/door";
import { Face } from "../personas/face";
import { Verdict } from "../personas/runs-side";
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
  // With every agent in view each row says which agent it rang.
  const columns = inView === "" ? "minmax(0,1.4fr) minmax(0,1fr) 96px 64px 84px 120px" : "minmax(0,1.6fr) 96px 64px 84px 120px";
  const labels = inView === "" ? ["Caller", "Agent", "When", "Turns>", "Time>", "How it went"] : ["Caller", "When", "Turns>", "Time>", "How it went"];
  const rows = (read.runs ?? []).filter((run) => shown(run, show));
  return (
    <section className="ui-tiles-block">
      <div className="runs-bar">
        <Chips options={SHOWS} value={show} onChange={setShow} />
      </div>
      {read.runs !== null && read.runs.length === 0 && <Empty>No simulation has run here yet. Choose a caller in New simulation to start the first one.</Empty>}
      {rows.length > 0 && (
        <div className="runs-table">
          <TableHead columns={columns} padding="9px 16px" labels={labels} />
          {rows.map((run) => (
            <TableRow key={run.call} columns={columns} to={`${base}/${run.call}`}>
              <span className="runs-who">
                <Face name={run.persona ?? "?"} size={28} />
                <span className="runs-name">{run.persona ?? "a caller"}</span>
              </span>
              {inView === "" && <span className="runs-faint">{run.agent}</span>}
              <span className="runs-faint">{ago(run.started_at)}</span>
              <span className="runs-num">{run.turns}</span>
              <span className="runs-faint runs-num">{run.ended_at === null ? "—" : duration(run)}</span>
              <span>{run.ended_at === null ? <Pill tone="green" small>on a call</Pill> : <Verdict run={run} />}</span>
            </TableRow>
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
