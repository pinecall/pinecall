/** Post-call actions, at the foot of the pane: keep as a case, write as a golden, judge again, the do-not-call list, or erase the call. */

import { type CallScore, CallScoreSchema } from "@pinecall/core/wire/events-call";
import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { post, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useScopes } from "../../../lib/whoami";
import { Button, Icon } from "../../../ui";
import { keepCall } from "../../cases";
import { promoteCall, type Promoted } from "../../evals/door";
import { eraseCall, optOut } from "../../org-data";

/**
 * Keep puts the call in the org's Cases, where the nightly plays it; Golden writes the same call
 * as a golden candidate into the directory of the agent's `pinecall start`, for one that belongs in
 * the repository; Re-judge runs the hang-up judges over the call again and writes their verdict on
 * its log — and is billed again, as the first judging was.
 * CLI equivalents: `pinecall cases keep`, `pinecall runs promote`, `pinecall eval`.
 */
export function Actions({ agent, call, number, onJudged }: { agent: string; call: string; number: string | null; onJudged: (score: CallScore) => void }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const scopes = useScopes();
  const [busy, setBusy] = useState<"" | "judge" | "keep" | "promote" | "erase" | "list">("");
  const [sure, setSure] = useState(false);
  const [listed, setListed] = useState(false);
  const [judged, setJudged] = useState(false);
  const [promoted, setPromoted] = useState<Promoted | null>(null);
  const [kept, setKept] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const does = async (what: "judge" | "keep" | "promote"): Promise<void> => {
    setBusy(what);
    setRefused(null);
    try {
      if (what === "judge") {
        onJudged(CallScoreSchema.parse(await post(credentials, `/v1/evals/judge/${encodeURIComponent(call)}?again=true`, {})));
        setJudged(true);
      }
      // Named by the call it came from, so a second keep of the same call is refused by name.
      else if (what === "keep") setKept((await keepCall(credentials, call, `kept-${call.slice(-6).toLowerCase()}`)).name);
      else setPromoted(await promoteCall(credentials, agent, call));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy("");
    }
  };

  // Nothing brings an erased call back, so the first press only asks; the trail keeps the row.
  const erase = async (): Promise<void> => {
    if (!sure) {
      setSure(true);
      return;
    }
    setBusy("erase");
    setRefused(null);
    try {
      await eraseCall(credentials, call);
      void navigate("/calls");
    } catch (failed) {
      setRefused(saidBy(failed));
      setBusy("");
    }
  };

  // The far end's number onto the org's do-not-call list: what the person asked for, from the page.
  const stopCalling = async (): Promise<void> => {
    if (number === null) return;
    setBusy("list");
    setRefused(null);
    try {
      await optOut(credentials, number);
      setListed(true);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy("");
    }
  };

  // The list is written through `talk` and the judges are asked through `evals`: a key without one
  // is not shown a button it would be refused.
  const mayList = number !== null && number.startsWith("+") && (scopes === null || scopes.includes("talk"));
  const mayJudge = scopes === null || scopes.includes("evals");

  return (
    <div className="over-acts">
      <Button disabled={busy !== "" || agent === "" || kept !== null} title="The org's Cases: approved, the nightly plays it" onClick={() => void does("keep")}>
        <Icon name="flask" size={14} />
        {busy === "keep" ? "Keeping…" : kept !== null ? "Kept as a case" : "Keep as a case"}
      </Button>
      <div className="over-acts-pair">
        <Button disabled={busy !== "" || agent === ""} title="A golden candidate in the agent's test/candidates, in the directory of pinecall start" onClick={() => void does("promote")}>
          <Icon name="golden" size={14} />
          {busy === "promote" ? "Writing…" : "Golden"}
        </Button>
        {mayJudge && (
          <Button disabled={busy !== ""} title="Run the judges over this call again — billed again, as the first judging was" onClick={() => void does("judge")}>
            <Icon name="refresh" size={14} />
            {busy === "judge" ? "Judging…" : "Re-judge"}
          </Button>
        )}
      </div>
      <div className="over-acts-quiet" onMouseLeave={() => setSure(false)}>
        {mayList && (
          <button type="button" className="over-acts-link" disabled={busy !== "" || listed} onClick={() => void stopCalling()}>
            {busy === "list" ? "Listing…" : listed ? `${number} is on the do-not-call list` : "Do not call"}
          </button>
        )}
        <button type="button" className="over-acts-link over-acts-erase" disabled={busy !== ""} onClick={() => void erase()}>
          {busy === "erase" ? "Erasing…" : sure ? "Erase it for good" : "Erase this call…"}
        </button>
      </div>
      {judged && <div className="over-result">Judged again: the verdict above is the new one, written on the call's log.</div>}
      {kept !== null && (
        <div className="over-result">
          <span className="over-result-lead">Kept</span>
          <Link to={`/a/${encodeURIComponent(agent)}/cases/${encodeURIComponent(kept)}`}>Open {kept} in Cases →</Link>
        </div>
      )}
      {promoted !== null && (
        <div className="over-result">
          <span className="over-result-lead">Written down</span>
          <span className="ui-fixed over-path">{promoted.path}</span>
          <span className="over-result-note">
            {promoted.candidate.turns.length} {promoted.candidate.turns.length === 1 ? "turn" : "turns"}
          </span>
          {promoted.notes.map((note) => (
            <span key={note} className="over-result-note over-result-line">
              {note}
            </span>
          ))}
        </div>
      )}
      {refused !== null && <div className="ui-refused">{refused}</div>}
    </div>
  );
}
