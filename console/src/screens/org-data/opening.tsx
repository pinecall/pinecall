/** What a spoken call says before its greeting: the AI disclosure an outbound call opens with, and the recording notice. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Pill, Switch, TextArea } from "../../ui";
import { NOTHING_SET, putPolicy, type Policy, type PolicyRow } from "./door";

const THE_PLATFORMS = "This is an automated assistant calling on behalf of {your org}.";

/**
 * Said in the agent's voice before its greeting and logged as its first turn, so a call can prove
 * what the person heard. The platform's sentence is spoken in the agent's language.
 */
export function OpeningCard({ policy, onSaved, onRefused }: { policy: PolicyRow | null; onSaved: (row: PolicyRow) => void; onRefused: (said: string | null) => void }): ReactNode {
  const credentials = useCredentials();
  const kept = policy?.policy ?? NOTHING_SET;
  const [words, setWords] = useState("");
  const [busy, setBusy] = useState(false);
  const disclosure = kept.disclosure ?? null;

  const save = async (changes: Partial<Policy>): Promise<void> => {
    setBusy(true);
    onRefused(null);
    try {
      onSaved(await putPolicy(credentials, kept, changes));
      setWords("");
    } catch (failed) {
      onRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  const [tone, which]: ["gray" | "green" | "red", string] =
    disclosure === null ? ["gray", "the platform's"] : disclosure === "" ? ["red", "none"] : ["green", "your own words"];

  return (
    <Card pad>
      <CardHead title="What a call says first" meta="every world" />
      <p className="data-sentence">
        <b>An outbound call opens with</b> <Pill tone={tone}>{which}</Pill>{" "}
        {disclosure === null && <>“{THE_PLATFORMS}”, in the agent's language.</>}
        {disclosure !== null && disclosure !== "" && <>“{disclosure}”</>}
      </p>
      {disclosure === "" && (
        <p className="data-sentence data-warn">
          Nothing is said before the greeting, so the agent's own greeting must say it is an automated assistant and whom it calls for:
          some US states require it, and the FCC treats an AI voice as an artificial one.
        </p>
      )}
      <div className="data-import">
        <TextArea rows={2} maxLength={500} aria-label="Your own opening sentence" value={words} placeholder="Hi, this is Ana, Clínica Norte's virtual assistant." onChange={(event) => setWords(event.target.value)} />
        <div className="data-form">
          <Button kind="primary" size="form" disabled={busy || words.trim() === ""} onClick={() => void save({ disclosure: words.trim() })}>
            Say these words
          </Button>
          {disclosure !== null && (
            <Button size="form" disabled={busy} onClick={() => void save({ disclosure: null })}>
              Use the platform's sentence
            </Button>
          )}
          {disclosure !== "" && (
            <Button size="form" kind="danger" disabled={busy} onClick={() => void save({ disclosure: "" })}>
              Say nothing
            </Button>
          )}
        </div>
      </div>
      <div className="data-form data-sentence-next">
        <Switch label="Recording notice" on={kept.recording_notice !== false} onChange={(on) => void save({ recording_notice: on })} />
        <span className="data-sentence">
          {kept.recording_notice !== false
            ? "A recorded call, inbound or outbound, then says “This call may be recorded.” An agent that records nothing says nothing."
            : "A recorded call says nothing of it: California, Florida and the other all-party states need the caller told."}
        </span>
      </div>
    </Card>
  );
}
