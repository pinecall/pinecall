/** The rules a call is held to, each with how often it held over the newest judged calls, and beside them the calls the picked one broke — each with the line it cites and the three moves on it. */

import { type Judgment } from "@pinecall/core/wire/events";
import { type EvalCase } from "@pinecall/core/wire/rest-evals";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { whoOn } from "@pinecall/core/calls";
import { useCredentials } from "@pinecall/core/credentials";
import { dayOf, webVisitor } from "../../lib/format";
import { rowAt } from "../../lib/harness";
import type { Scored } from "../../lib/use-scores";
import { Avatar } from "../../ui";
import { decideCase, keepCall } from "../cases";
import type { JudgeRow } from "./judges-door";

/** One rule as the list draws it: its judge, its words, and how it answered over the calls read. */
export interface Rule {
  name: string;
  said: string;
  held: number;
  settled: number;
}

/** The rules in force, by how often they broke, each counted over the calls read; a judge that answered and is not listed is still a rule. */
export function rulesOf(judges: readonly JudgeRow[] | null, scored: readonly Scored[]): Rule[] {
  const rules = new Map<string, Rule>();
  for (const judge of judges ?? []) {
    if (judge.on) rules.set(judge.name, { name: judge.name, said: judge.summary ?? judge.question, held: 0, settled: 0 });
  }
  for (const row of scored) {
    for (const judge of row.score?.judges ?? []) {
      if (judge.verdict !== "held" && judge.verdict !== "broken") continue;
      const rule = rules.get(judge.name) ?? { name: judge.name, said: judge.name, held: 0, settled: 0 };
      rules.set(judge.name, { ...rule, held: rule.held + (judge.verdict === "held" ? 1 : 0), settled: rule.settled + 1 });
    }
  }
  return [...rules.values()].sort((one, other) => other.settled - other.held - (one.settled - one.held) || other.settled - one.settled);
}

// A rule that holds this often is green, a little less amber, and under it red.
function toneOf(share: number): "green" | "amber" | "red" {
  return share >= 0.95 ? "green" : share >= 0.9 ? "amber" : "red";
}

export function Rules({ rules, picked, onPick, agent }: { rules: readonly Rule[]; picked: string | null; onPick: (name: string) => void; agent: string }): ReactNode {
  return (
    <div className="qly-card">
      <div className="qly-card-head">
        <span className="qly-card-title">Rules</span>
        <Link to={rowAt(agent, "judges")} className="qly-card-link">
          + New judge
        </Link>
      </div>
      {rules.length === 0 && <p className="qly-quiet">No judge is on: the calls are held to no rule yet.</p>}
      {rules.map((rule) => {
        const share = rule.settled === 0 ? null : rule.held / rule.settled;
        const broke = rule.settled - rule.held;
        return (
          <button key={rule.name} type="button" className={rule.name === picked ? "qly-rule qly-rule-on" : "qly-rule"} onClick={() => onPick(rule.name)}>
            <span className="qly-rule-words">
              <span className="qly-rule-said">{rule.said}</span>
              <span className="qly-rule-name">
                {rule.name} · {rule.settled} judged
              </span>
            </span>
            <span className="qly-rule-rate">
              {share === null ? (
                <span className="qly-rule-pct qly-faint">—</span>
              ) : (
                <>
                  <span className={`qly-rule-pct qly-tone-${toneOf(share)}`}>{Math.round(share * 100)}%</span>
                  <span className="qly-rule-track">
                    <span className={`qly-rule-fill qly-fill-${toneOf(share)}`} style={{ width: `${share * 100}%` }} />
                  </span>
                </>
              )}
            </span>
            <span className={broke > 0 ? "qly-rule-broke" : "qly-rule-broke qly-faint"}>{broke > 0 ? `${broke} broke` : "none"}</span>
          </button>
        );
      })}
    </div>
  );
}

/** The calls the picked rule broke, newest first: who, whose and when, the line it cites, why, and what a person does next. */
export function BrokeIt({ rule, scored, cases, agent }: { rule: Rule | undefined; scored: readonly Scored[]; cases: readonly EvalCase[]; agent: string }): ReactNode {
  const broke = rule === undefined ? [] : scored.flatMap((row) => {
    const judgment = row.score?.judges.find((judge) => judge.name === rule.name && judge.verdict === "broken");
    return judgment === undefined ? [] : [{ row, judgment }];
  });
  return (
    <div className="qly-card">
      <div className="qly-card-head qly-card-head-stacked">
        <span className="qly-card-title">Calls that broke it</span>
        {rule !== undefined && (
          <span className="qly-card-sub">
            {rule.said} · {broke.length} of {rule.settled} calls
          </span>
        )}
      </div>
      {rule === undefined ? (
        <p className="qly-quiet">Pick a rule to see the calls it broke.</p>
      ) : broke.length === 0 ? (
        <p className="qly-quiet">It held on every call read.</p>
      ) : (
        broke.map(({ row, judgment }) => (
          <BrokeCall key={row.line.call} row={row} judgment={judgment} kept={cases.find((one) => one.source_call === row.line.call && one.status === "pending")} agent={agent} />
        ))
      )}
    </div>
  );
}

function BrokeCall({ row, judgment, kept, agent }: { row: Scored; judgment: Judgment; kept: EvalCase | undefined; agent: string }): ReactNode {
  const credentials = useCredentials();
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const line = row.line;
  const who = whoOn(line, webVisitor);
  const seq = judgment.evidence.seqs[0];

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

  return (
    <div className="qly-call">
      <div className="qly-call-who">
        <Avatar name={who} size={28} round />
        <span className="qly-call-words">
          <span className="qly-call-name">{who}</span>
          <span className="qly-call-sub">
            {line.agent} · {dayOf(line.started_at)}
          </span>
        </span>
      </div>
      <div className="qly-call-proof">
        {(seq !== undefined || judgment.evidence.said != null) && (
          <span className="qly-call-said">
            {seq !== undefined && <span className="qly-call-seq">#{seq}</span>}
            {judgment.evidence.said != null && <span>“{judgment.evidence.said}”</span>}
          </span>
        )}
        <span className="qly-call-why">{judgment.reason}</span>
      </div>
      <div className="qly-call-moves">
        <Link to={`${rowAt(agent, "calls")}/${line.call}${seq === undefined ? "" : `#seq-${seq}`}`}>Open the call</Link>
        <button
          type="button"
          className="qly-call-move"
          disabled={busy}
          onClick={() =>
            void does(async () => {
              await keepCall(credentials, line.call, `kept-${line.call.slice(-6).toLowerCase()}`);
              return "Kept as a case.";
            })
          }
        >
          Keep as a case
        </button>
        {/* The judge is told it was wrong through the case its break opened: no case waiting, nothing to tell. */}
        {kept !== undefined && (
          <button
            type="button"
            className="qly-call-move"
            disabled={busy}
            title={`Dismiss the case, and mark ${judgment.name} as wrong on it`}
            onClick={() =>
              void does(async () => {
                await decideCase(credentials, kept.id, { status: "dismissed", judge_was_wrong: judgment.name });
                return `${judgment.name} marked wrong; the case is dismissed.`;
              })
            }
          >
            Judge was wrong
          </button>
        )}
        {said !== null && <span className="qly-call-done">{said}</span>}
      </div>
    </div>
  );
}
