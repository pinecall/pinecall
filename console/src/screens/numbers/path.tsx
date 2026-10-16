/** A number opened: the four steps a call to it goes through, each with what would fix it, and its moves. */

import { useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { ago } from "../../lib/format";
import { Button } from "../../ui";
import { readPath, type Answering, type NumberPath } from "./door";

const STEP_NAMED: Record<NumberPath["steps"][number]["step"], string> = {
  carrier: "Carrier",
  fence: "Fence",
  world: "World",
  agent: "Agent",
};

const MARK: Record<NumberPath["rings"], string> = { ok: "✓", waiting: "…", broken: "!" };

/** What the drawer is told: the row it opened under, and the moves it offers. */
export interface PathProps {
  row: Answering;
  busy: boolean;
  onMove: () => void;
  onRemove: () => void;
}

/** Read when opened, not for every row: it is the one place the carrier's own API is asked. */
export function Path({ row, busy, onMove, onRemove }: PathProps): ReactNode {
  const credentials = useCredentials();
  const number = row.route.number ?? "";
  const [path, setPath] = useState<NumberPath | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readPath(credentials, number).then(
      (found) => {
        if (!gone) setPath(found);
      },
      (failed: unknown) => {
        if (!gone) setRefused(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, number, row.rings, row.last_call_at]);

  const other = row.route.env === "production" ? "sandbox" : "production";
  return (
    <div className="num-path">
      <div className="num-path-title">What a call to {prettyNumber(number)} goes through</div>
      {path === null ? (
        <div className="num-path-reading">{refused ?? "Reading…"}</div>
      ) : (
        <ol className="num-steps-path">
          {path.steps.map((step) => (
            <li key={step.step} className="num-step-path">
              <span className={`num-step-mark num-step-${step.state}`} aria-label={step.state}>
                {MARK[step.state]}
              </span>
              <span className="num-step-name">{STEP_NAMED[step.step]}</span>
              <span className="num-step-says">{step.says}</span>
              {step.fix != null && <span className="num-step-fix">{step.fix}</span>}
            </li>
          ))}
        </ol>
      )}
      <div className="num-path-foot">
        <span>{row.last_call_at == null ? "No call has reached the box yet" : `Last call ${ago(row.last_call_at)}`}</span>
        <span className="num-path-moves">
          <Button size="sm" onClick={onMove} disabled={busy} title={`Its row and the two rules; the carrier is not touched.`}>
            Move to {other}
          </Button>
          <Button size="sm" kind="danger" onClick={onRemove} disabled={busy} title="The number stops reaching this agent. It stays in your account.">
            Remove
          </Button>
        </span>
      </div>
    </div>
  );
}
