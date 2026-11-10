/** A judge tried on an agent's newest finished calls before it is trusted or kept: each call's answer and why, the evals it spent and what they cost. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { money } from "../lib/format";
import { useOrg } from "../lib/org";
import { Select } from "../ui/select";
import { tryJudge, type JudgeRequest, type JudgeTried } from "./door";
import { answerOf } from "./fold";

const COUNTS = ["3", "5", "10", "20"].map((count) => ({ value: count, label: `Last ${count} calls` }));

/** `written` is the judge as a form holds it, tried unsaved; null tries the judge the name already is. With no agent in view, the person picks whose calls. */
export function TryJudge({ agent, name, written, ready = true }: { agent: string; name: string; written: JudgeRequest | null; /** False while the form is not a judge yet. */ ready?: boolean }): ReactNode {
  const credentials = useCredentials();
  const { agents } = useOrg();
  const [picked, setPicked] = useState(agent);
  const [last, setLast] = useState("5");
  const [trying, setTrying] = useState(false);
  const [tried, setTried] = useState<JudgeTried | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const whose = agent === "" ? picked : agent;

  const run = async (): Promise<void> => {
    setTrying(true);
    setRefused(null);
    try {
      setTried(await tryJudge(credentials, whose, name, written, Number(last)));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setTrying(false);
    }
  };

  return (
    <div className="jd-try">
      <div className="jd-try-ask">
        {agent === "" && <Select label="Whose calls" placeholder="Whose calls" value={picked} items={agents.map((one) => ({ value: one.slug, label: one.slug }))} onChange={setPicked} />}
        <Select label="How many calls" searchable={false} value={last} items={COUNTS} onChange={setLast} />
        <button type="button" className="app-button jd-try-go" disabled={trying || whose === "" || name === "" || !ready} onClick={() => void run()}>
          {trying ? "Asking…" : "Try it"}
        </button>
      </div>
      <p className="dash-quiet">Asks the judge model as a hang-up does, so each answer is an eval. Nothing is written to the calls.</p>
      {refused !== null && <p className="app-refused">{refused}</p>}
      {tried !== null && (
        <div className="jd-tried">
          <span className="dash-quiet">
            {tried.rows.length} {tried.rows.length === 1 ? "call" : "calls"} · {tried.evals} {tried.evals === 1 ? "eval" : "evals"} · {money(tried.cost_usd)}
          </span>
          {tried.rows.length === 0 && <p className="dash-quiet">{whose} has no finished call to ask it of yet.</p>}
          {tried.rows.map((row) => {
            const verdict = row.judgment?.verdict;
            return (
              <Link key={row.call} to={`/calls/${encodeURIComponent(row.call)}`} className="jd-tried-row">
                <span className={verdict === "broken" ? "jd-answer jd-answer-bad" : verdict === "held" ? "jd-answer jd-answer-good" : "jd-answer"}>{row.judgment === null ? "Not judged" : answerOf(row.judgment)}</span>
                <span className="jd-tried-why">{row.judgment?.reason ?? row.not_judged ?? ""}</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
