/** What a person decides of a case: approve it into the nightly, dismiss it, or open it again. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Input } from "../../ui";
import { decideCase, type CaseDecision, type EvalCase } from "./door";

export function Decide({ kept, onDecided }: { kept: EvalCase; onDecided: (kept: EvalCase) => void }): ReactNode {
  const credentials = useCredentials();
  // Dismissing says why, so it opens a choice before it writes anything.
  const [dismissing, setDismissing] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const decide = async (decision: CaseDecision): Promise<void> => {
    if (busy) return;
    setBusy(true);
    setRefused(null);
    try {
      onDecided(await decideCase(credentials, kept.id, decision));
      setDismissing(false);
      setNote("");
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };
  const noted = note.trim() === "" ? {} : { note: note.trim() };

  return (
    <div className="cs-decide">
      <div className="cs-doc-actions">
        {kept.status === "pending" ? (
          <>
            <Button kind="primary" size="sm" disabled={busy} title="The nightly plays it from now on" onClick={() => void decide({ status: "approved" })}>
              Approve
            </Button>
            <Button size="sm" disabled={busy} onClick={() => setDismissing(!dismissing)}>
              Dismiss…
            </Button>
          </>
        ) : (
          <Button size="sm" disabled={busy} onClick={() => void decide({ status: "pending" })}>
            Open it again
          </Button>
        )}
      </div>
      {dismissing && (
        <div className="cs-dismiss">
          <Input value={note} placeholder="Why, for the judge's calibration (optional)" aria-label="Why" onChange={(event) => setNote(event.target.value)} />
          {kept.broke.map((one) => (
            <Button key={one.judge} size="sm" disabled={busy} onClick={() => void decide({ status: "dismissed", judge_was_wrong: one.judge, ...noted })}>
              {one.judge} was wrong: it should have held
            </Button>
          ))}
          <Button size="sm" disabled={busy} onClick={() => void decide({ status: "dismissed" })}>
            Not worth keeping
          </Button>
        </div>
      )}
      {refused !== null && <p className="cs-bad">{refused}</p>}
    </div>
  );
}
