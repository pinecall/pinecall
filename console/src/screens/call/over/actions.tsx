/** Post-call actions: re-check by code (ring 3), keep as a case or write as a candidate, or erase the call. */

import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useScopes } from "../../../lib/whoami";
import { Button, Pill, type Tone } from "../../../ui";
import { keepCall } from "../../cases";
import { promoteCall, replayCall, type Promoted, type Replayed } from "../../evals/door";
import { eraseCall, optOut } from "../../org-data";

// Operator-facing labels for ring-3 verdicts, distinct from judge verdicts.
const TONE: Record<string, Tone> = { held: "green", broken: "red", deferred: "amber", skipped: "muted" };

/**
 * Ring 3 rebuilds the call from its log without re-running it. Keep puts the call in the org's
 * Cases, where the nightly plays it; a candidate is the same golden written into the directory of
 * the agent's `pinecall start`, for one that names the code and belongs in the repository.
 * CLI equivalents: `pinecall eval`, `pinecall cases keep`, `pinecall runs promote`.
 */
export function Actions({ agent, call, number }: { agent: string; call: string; number: string | null }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const scopes = useScopes();
  const [busy, setBusy] = useState<"" | "check" | "keep" | "promote" | "erase" | "list">("");
  const [sure, setSure] = useState(false);
  const [listed, setListed] = useState(false);
  const [replayed, setReplayed] = useState<Replayed | null>(null);
  const [promoted, setPromoted] = useState<Promoted | null>(null);
  const [kept, setKept] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const does = async (what: "check" | "keep" | "promote"): Promise<void> => {
    setBusy(what);
    setRefused(null);
    try {
      if (what === "check") setReplayed(await replayCall(credentials, call));
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

  // The list is written through `talk`; a key without it is not shown a button it would be refused.
  const mayList = number !== null && number.startsWith("+") && (scopes === null || scopes.includes("talk"));

  return (
    <div className="over-acts">
      <div className="over-buttons" onMouseLeave={() => setSure(false)}>
        <Button size="sm" disabled={busy !== ""} onClick={() => void does("check")}>
          {busy === "check" ? "Checking…" : "Re-check by code"}
        </Button>
        <Button size="sm" disabled={busy !== "" || agent === "" || kept !== null} title="The org's Cases: approved, the nightly plays it" onClick={() => void does("keep")}>
          {busy === "keep" ? "Keeping…" : kept !== null ? "Kept as a case" : "Keep as a case"}
        </Button>
        <Button size="sm" disabled={busy !== "" || agent === ""} title="A golden file in the agent's test/candidates, in the directory of pinecall start" onClick={() => void does("promote")}>
          {busy === "promote" ? "Writing…" : "Write as a candidate"}
        </Button>
        <Button size="sm" kind={sure ? "danger" : "secondary"} disabled={busy !== ""} onClick={() => void erase()}>
          {busy === "erase" ? "Erasing…" : sure ? "Erase it for good" : "Erase this call"}
        </Button>
        {mayList && (
          <Button size="sm" disabled={busy !== "" || listed} onClick={() => void stopCalling()}>
            {busy === "list" ? "Listing…" : listed ? `${number} on the do-not-call list` : "Do not call this number"}
          </Button>
        )}
      </div>
      {replayed !== null && (
        <div className="over-result">
          <span className="over-result-lead">{replayed.passed ? "Holds by code" : "Does not hold by code"}</span>
          {replayed.verdicts.map((verdict) => (
            <Pill key={verdict.check} tone={TONE[verdict.status] ?? "muted"}>
              {verdict.check} {verdict.status}
            </Pill>
          ))}
        </div>
      )}
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
