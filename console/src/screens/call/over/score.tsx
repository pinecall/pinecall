/** Post-call score card: each judge's answer (held, broken, N/A, a choice or a score), cited evidence, the evals billed and the judging cost. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type Judgment } from "@pinecall/core/wire/events";
import { type CallScore, CallScoreSchema } from "@pinecall/core/wire/events-call";
import { TERMINAL_EVENT } from "@pinecall/core/wire/registry";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { GatewayError, post } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { usd } from "../../../lib/format";
import { answerOf } from "../../../lib/judgment";
import { useScopes } from "../../../lib/whoami";
import { Button, Card, CardHead, Pill, type Tone } from "../../../ui";

const VERDICT_TONE: Record<string, Tone> = { held: "green", broken: "red", classified: "indigo", na: "muted", deferred: "amber", skipped: "muted" };

/** The `call.score` verdict from the log, or null if the call is not scored. */
export function scoreIn(entries: Entry[]): CallScore | null {
  const sealed = [...entries].reverse().find((entry) => entry.type === TERMINAL_EVENT);
  return sealed === undefined ? null : CallScoreSchema.parse(sealed.data);
}

// Judges that returned nothing are drawn dim, never green, so coverage is not overstated.
// `compact`, beside the call: each judge one line, its reason a click away, the bill left to the full page.
export function ScoreCard({
  call,
  base,
  score: sealed,
  turns,
  ended,
  compact = false,
}: {
  call: string;
  base: string;
  score: CallScore | null;
  turns: number;
  ended: boolean;
  compact?: boolean;
}): ReactNode {
  // A verdict requested here overrides the logged one on this screen.
  const [asked, setAsked] = useState<CallScore | null>(null);
  const score = asked ?? sealed;
  return (
    <Card>
      <CardHead title="Score" meta={score !== null && score.passed != null ? `${held(score)} of ${settled(score)} held` : undefined} />
      <div className="ui-card-body">
        {score === null ? (
          <>
            <div className="over-standing over-standing-amber">Not scored yet</div>
            <p className="over-sentence">
              The call is still running, or its log was sealed before the judges existed. Ask for one with{" "}
              <span className="ui-fixed">pinecall eval {call}</span>.
            </p>
            {ended && <AttachAJudge call={call} onJudged={setAsked} />}
          </>
        ) : score.passed == null && !score.judges.some(answered) ? (
          <>
            <div className="over-standing over-standing-amber">No judge was given to this session</div>
            {saysMore(score.not_judged) && <p className="over-sentence">{score.not_judged}</p>}
            <p className="over-sentence">{billOf(score, turns)}</p>
            {ended && <AttachAJudge call={call} onJudged={setAsked} />}
          </>
        ) : (
          <>
            {score.passed == null ? (
              <div className="over-standing over-standing-amber">No judge held or broke: each classified the call or did not apply</div>
            ) : (
              <div className={score.passed ? "over-standing over-standing-green" : "over-standing over-standing-red"}>{score.passed ? "Passed" : "Did not pass"}</div>
            )}
            <div className="over-judges">
              {score.judges.map((judge) => (
                <JudgeRow key={judge.name} base={base} call={call} judgment={judge} compact={compact} />
              ))}
              {(score.panel ?? [])
                .filter((name) => !score.judges.some((judge) => judge.name === name))
                .map((name) => (
                  <div key={name} className="over-judge">
                    <div className="over-judge-line">
                      <span className="over-judge-name">{name}</span>
                      <Pill tone="muted">on the panel</Pill>
                    </div>
                    <div className="over-judge-reason">Was run over this call and answered nothing.</div>
                  </div>
                ))}
            </div>
            {!compact && <p className="over-sentence">{billOf(score, turns)}</p>}
          </>
        )}
      </div>
    </Card>
  );
}

function JudgeRow({ base, call, judgment, compact }: { base: string; call: string; judgment: Judgment; compact: boolean }): ReactNode {
  if (compact) {
    return (
      <details className="over-judge over-judge-folded">
        <summary className="over-judge-line">
          <span className="over-judge-name">{judgment.name}</span>
          <Pill tone={VERDICT_TONE[judgment.verdict] ?? "muted"}>{answerOf(judgment)}</Pill>
        </summary>
        <div className="over-judge-reason">
          {judgment.reason}
          {judgment.evidence.said != null && <span className="over-judge-said"> “{judgment.evidence.said}”</span>}
        </div>
        {judgment.evidence.seqs.length > 0 && (
          <div className="over-judge-line">
            {judgment.evidence.seqs.map((seq) => (
              <Link key={seq} className="over-seq" to={`${base}/${call}#seq-${seq}`}>
                seq {seq}
              </Link>
            ))}
          </div>
        )}
      </details>
    );
  }
  return (
    <div className="over-judge over-judge-full">
      <span className="over-judge-name">{judgment.name}</span>
      <span>
        <Pill tone={VERDICT_TONE[judgment.verdict] ?? "muted"}>{answerOf(judgment)}</Pill>
      </span>
      <div className="over-judge-body">
        <div className="over-judge-reason">{judgment.reason}</div>
        {judgment.evidence.said != null && <blockquote className="over-judge-quote">“{judgment.evidence.said}”</blockquote>}
        {judgment.evidence.seqs.length > 0 && (
          <div className="over-judge-line">
            <span className="over-judge-cited">In the conversation:</span>
            {judgment.evidence.seqs.map((seq) => (
              <Link key={seq} className="over-seq" to={`${base}/${call}#seq-${seq}`}>
                #{seq}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function saysMore(reason: string | null | undefined): reason is string {
  return reason !== null && reason !== undefined && reason.trim().toLowerCase() !== "no judge was given to this session";
}

function held(score: CallScore): number {
  return score.judges.filter((judge) => judge.verdict === "held").length;
}

// Only held and broken pass or fail a call: N/A and a classification are answers, never a verdict.
function settled(score: CallScore): number {
  return score.judges.filter((judge) => judge.verdict === "held" || judge.verdict === "broken").length;
}

function answered(judgment: Judgment): boolean {
  return judgment.verdict !== "deferred" && judgment.verdict !== "skipped";
}

function billOf(score: CallScore, turns: number): string {
  const replayed = `${turns === 1 ? "One turn" : `${turns} turns`} replayed from the log`;
  if (score.judge_calls === 0) return `${replayed}; no judge asked the model, and nothing was billed.`;
  const evals = score.evals ?? 0;
  const billed = score.own_key === true ? `${evals} eval${evals === 1 ? "" : "s"} on your own key, not billed` : `${evals} eval${evals === 1 ? "" : "s"} billed`;
  return `${replayed}; ${score.judge_calls} judge call${score.judge_calls === 1 ? "" : "s"} for ${usd(score.judge_cost_usd)} · ${billed}.`;
}

/** Run the hang-up judges on an unscored call (POST /v1/evals/judge/{call}); the verdict is written to its log. */
function AttachAJudge({ call, onJudged }: { call: string; onJudged: (score: CallScore) => void }): ReactNode {
  const credentials = useCredentials();
  const scopes = useScopes();
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  if (scopes !== null && !scopes.includes("evals")) return null;

  const judge = async (): Promise<void> => {
    setBusy(true);
    setRefused(null);
    try {
      onJudged(CallScoreSchema.parse(await post(credentials, `/v1/evals/judge/${encodeURIComponent(call)}`, {})));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="over-attach">
      <Button size="md" disabled={busy} onClick={() => void judge()}>
        {busy ? "Judging…" : "Attach a judge"}
      </Button>
      {refused !== null && <p className="over-sentence over-refused-line">{refused}</p>}
    </div>
  );
}
