/** The right side: what this caller has actually done — every simulation of it, newest first. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { ago, duration, usd } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import { Button, Dot, Pill } from "../../ui";
import type { Persona, PersonaRun } from "./door";
import { usePersonaRuns } from "./use-persona-runs";

/**
 * One pane, one caller. It is a list of CALLS — each row opens that conversation — and it is the key's
 * own corner: a developer sees the runs they ran, production sees production's. A caller that has
 * never been called says so and points at the screen that calls it.
 */
export function RunsSide({ inView, persona }: { inView: string; persona: Persona }): ReactNode {
  const { runs, total, asking, error, more } = usePersonaRuns(persona.agent, persona.name);
  const simulations = rowAt(inView, "simulations");
  return (
    <aside className="psn-runs" aria-label={`what ${persona.name} has done`}>
      <div className="psn-runs-head">
        <div className="psn-titles">
          <span className="psn-title">Runs</span>
          <span className="psn-count">{runs === null ? "" : total}</span>
        </div>
        <p className="psn-lede">Every simulation this caller has run, newest first. A row opens it in Simulations.</p>
      </div>
      <div className="psn-runs-list">
        {runs?.map((run) => <Run key={run.call} run={run} to={`${simulations}/${run.call}`} />)}
        {runs !== null && runs.length === 0 && !asking && (
          <p className="psn-empty">
            Nobody has called as {persona.name} yet. Put them on {persona.agent} in{" "}
            <Link to={`${simulations}?agent=${encodeURIComponent(persona.agent)}&persona=${encodeURIComponent(persona.name)}`}>Simulations</Link>, or
            run <code>pinecall simulate --persona {persona.name}</code>.
          </p>
        )}
        {runs === null && asking && <p className="psn-empty">Asking the gateway…</p>}
        {more !== null && (
          <div className="psn-runs-more">
            <Button size="sm" disabled={asking} onClick={more}>
              {asking ? "Reading…" : `Show more (${String(total - (runs?.length ?? 0))} older)`}
            </Button>
          </div>
        )}
      </div>
      {error !== null && <p className="psn-empty psn-bad">{error}</p>}
    </aside>
  );
}

// One run: which agent answered and when, how it went, and the line the call came to. A run still
// going has no end and no verdict yet, and says that rather than showing an empty one.
function Run({ run, to }: { run: PersonaRun; to: string }): ReactNode {
  const running = run.ended_at === null;
  return (
    <Link to={to} className="psn-run">
      <span className="psn-run-top">
        <span className="psn-run-agent">{run.agent}</span>
        {running && <Dot tone="green" small />}
        <span className="psn-run-when">{ago(run.started_at)}</span>
      </span>
      <span className="psn-run-marks">
        <Verdict run={run} />
        <span className="psn-run-fact">
          {String(run.turns)} {run.turns === 1 ? "turn" : "turns"}
        </span>
        {!running && <span className="psn-run-fact">{duration(run)}</span>}
        {run.cost_usd !== null && <span className="psn-run-fact">{usd(run.cost_usd)}</span>}
      </span>
      {run.outcome !== null && <span className="psn-run-outcome">{run.outcome}</span>}
      {run.score?.passed === false && run.score.reason !== null && <span className="psn-run-broke">{run.score.reason}</span>}
    </Link>
  );
}

// What the judges answered, in one mark. Nobody judged the run is not a failure: it is a run that
// was never scored, and the pane says exactly that.
export function Verdict({ run }: { run: PersonaRun }): ReactNode {
  if (run.ended_at === null) return <Pill tone="green" small>on a call</Pill>;
  if (run.score === null) {
    return (
      <Pill tone="muted" small>
        {run.end_reason === null ? "not judged" : run.end_reason.replace(/_/g, " ")}
      </Pill>
    );
  }
  return (
    <Pill tone={run.score.passed ? "green" : "red"} small>
      {run.score.passed ? "held" : "broke"} {String(run.score.held)}/{String(run.score.judged)}
    </Pill>
  );
}
