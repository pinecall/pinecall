/** A judge tried on the agent's newest finished calls before it is kept: each call's answer, the evals it spent and what they cost. Nothing is written. */

import { useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { usd } from "../../lib/format";
import { answerOf } from "../../lib/judgment";
import { Button, Input } from "../../ui";
import { tryJudge, type JudgeRequest, type JudgeTried } from "./judges-door";

const MOST = 50;

/**
 * `written` is the judge as the form holds it, tried unsaved; null tries the judge `name` already
 * is (Pinecall's, the org's or the agent's own). A try asks the judge model as the seal does, so
 * each answer is an eval.
 */
export function TryJudge({ agent, name, written }: { agent: string; name: string; written: JudgeRequest | null }): ReactNode {
  const credentials = useCredentials();
  const [last, setLast] = useState("5");
  const [trying, setTrying] = useState(false);
  const [tried, setTried] = useState<JudgeTried | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const count = Number(last);
  const ready = Number.isInteger(count) && count >= 1 && count <= MOST && name !== "" && !trying;

  const run = async (): Promise<void> => {
    setTrying(true);
    setRefused(null);
    try {
      setTried(await tryJudge(credentials, agent, { ...(written ?? {}), name, last: count }));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setTrying(false);
    }
  };

  return (
    <div className="qly-try">
      <div className="qly-form-foot">
        <span className="qly-hint">Try on {agent}&apos;s last</span>
        <Input size="sm" className="qly-try-count" value={last} inputMode="numeric" aria-label="How many calls" onChange={(event) => setLast(event.target.value)} />
        <span className="qly-hint">calls</span>
        <Button size="sm" disabled={!ready} onClick={() => void run()}>
          {trying ? "Asking…" : "Try"}
        </Button>
        {refused !== null && <span className="qly-bad">{refused}</span>}
      </div>
      {tried !== null && (
        <div className="qly-tried">
          <p className="qly-hint">
            {tried.rows.length} calls · {tried.evals} evals · {usd(tried.cost_usd)}
          </p>
          {tried.rows.map((row) => (
            <div key={row.call} className="qly-tried-row">
              <span className="qly-tried-call">{row.call}</span>
              <span className={row.judgment?.verdict === "broken" ? "qly-tried-answer qly-pct-bad" : "qly-tried-answer"}>{row.judgment === null ? "—" : row.judgment.verdict === "broken" ? "broke" : answerOf(row.judgment)}</span>
              <span className="qly-asks">{row.judgment?.reason ?? row.not_judged ?? ""}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
