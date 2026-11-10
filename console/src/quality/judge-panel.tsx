/** One judge in the side panel: what it asks, how it held, and the calls it broke, each with the line it cites, why, and what a person does next. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { whoOn } from "@pinecall/core/calls";
import { useCredentials } from "@pinecall/core/credentials";
import { keepCall } from "../calls/door";
import { Face } from "../calls/face";
import { dayAndTime, webVisitor } from "../calls/format";
import { percent } from "../lib/format";
import { decideCase } from "../test/door";
import { SidePanel } from "../ui/side-panel";
import type { EvalCase } from "./door";
import { answersOf, brokenBy, readsOf, toneOf, whenOf, whoseOf, type Break, type Rule } from "./rules";
import type { Scored } from "./use-scores";

function BrokeCall({ broke, waiting }: { broke: Break; /** The case this break opened, while it waits for a person. */ waiting: EvalCase | undefined }): ReactNode {
  const credentials = useCredentials();
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { judgment } = broke;
  const line = broke.row.line;
  const who = whoOn(line, webVisitor);
  const seq = judgment.evidence.seqs[0];
  const quoted = judgment.evidence.said;

  const does = async (doing: () => Promise<string>): Promise<void> => {
    setBusy(true);
    try {
      setSaid(await doing());
    } catch (failed) {
      setSaid(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };
  const keep = (): void =>
    void does(async () => {
      await keepCall(credentials, line.call, `kept-${line.call.slice(-6).toLowerCase()}`);
      return "Kept as a case.";
    });
  const wrong = (kept: EvalCase): void =>
    void does(async () => {
      await decideCase(credentials, kept.id, { status: "dismissed", judge_was_wrong: judgment.name });
      return `${judgment.name} marked wrong, and the case is dismissed.`;
    });

  return (
    <div className="ql-call">
      <div className="ql-call-who">
        <Face name={who} />
        <span className="ql-row-main">
          <span className="ql-row-title dash-clip">{who}</span>
          <span className="ql-row-under dash-clip">
            {line.agent} · {dayAndTime(line.started_at)}
          </span>
        </span>
      </div>
      {(seq !== undefined || (quoted !== null && quoted !== undefined)) && (
        <p className="ql-call-said">
          {seq !== undefined && <span className="ql-call-seq">#{seq}</span>}
          {quoted !== null && quoted !== undefined && <span>“{quoted}”</span>}
        </p>
      )}
      <p className="ql-call-why">{judgment.reason}</p>
      <div className="ql-call-moves">
        <Link to={`/calls/${encodeURIComponent(line.call)}`} className="app-button ql-button-link">
          Open the call
        </Link>
        <button type="button" className="app-button" disabled={busy} onClick={keep}>
          Keep as a case
        </button>
        {/* The judge is told it was wrong through the case its break opened: no case waiting, nothing to tell. */}
        {waiting !== undefined && (
          <button type="button" className="app-button" disabled={busy} title={`Dismiss the case, and mark ${judgment.name} as wrong on it`} onClick={() => wrong(waiting)}>
            Judge was wrong
          </button>
        )}
      </div>
      {said !== null && <p className="ql-said">{said}</p>}
    </div>
  );
}

export function JudgePanel({ rule, scored, cases, onClose }: { rule: Rule; scored: readonly Scored[]; cases: readonly EvalCase[]; onClose: () => void }): ReactNode {
  const share = rule.settled === 0 ? null : rule.held / rule.settled;
  const broke = brokenBy(rule.name, scored);
  const judge = rule.judge;
  const reads = judge === null ? "" : readsOf(judge);
  return (
    <SidePanel title={rule.name} icon="judges" about={judge?.question ?? rule.said} onClose={onClose}>
      <div className="ql-held">
        <div className="ql-held-line">
          <span className={share === null ? "ql-figure dash-quiet" : `ql-figure ql-tone-${toneOf(share)}`}>{share === null ? "—" : percent(share)}</span>
          <span className="dash-quiet">{rule.settled === 0 ? "It has answered no call read yet." : `Held on ${rule.held} of ${rule.settled} judged calls.`}</span>
        </div>
        <span className="ql-track ql-track-wide" aria-hidden="true">
          {share !== null && <span className={`ql-fill-${toneOf(share)}`} style={{ width: `${share * 100}%` }} />}
        </span>
      </div>

      {judge !== null && (
        <dl className="ql-facts">
          <div>
            <dt>It answers</dt>
            <dd>{answersOf(judge)}</dd>
          </div>
          <div>
            <dt>It runs on</dt>
            <dd>{whenOf(judge)}</dd>
          </div>
          {reads !== "" && (
            <div>
              <dt>It also reads</dt>
              <dd className="dash-first">{reads}</dd>
            </div>
          )}
          <div>
            <dt>Whose it is</dt>
            <dd>{whoseOf(judge)}</dd>
          </div>
        </dl>
      )}

      <div className="ql-calls">
        <span className="dash-eyebrow">Calls it broke</span>
        {broke.length === 0 ? (
          <p className="dash-quiet">It held on every call read.</p>
        ) : (
          broke.map((one) => <BrokeCall key={one.row.line.call} broke={one} waiting={cases.find((kept) => kept.source_call === one.row.line.call && kept.status === "pending")} />)
        )}
      </div>
    </SidePanel>
  );
}
