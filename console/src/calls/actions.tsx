/** What a person does with a call that is over: keep it as a case, write it as a golden, judge it again, stop calling the number, or erase it. */

import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { type CallScore } from "@pinecall/core/wire/events-call";
import { useOrg } from "../lib/org";
import { eraseCall, judgeAgain, keepCall, optOut, promoteCall, type Promoted } from "./door";

type Busy = "" | "judge" | "keep" | "promote" | "erase" | "list";

export function Actions({ agent, call, number, onJudged }: { agent: string; call: string; number: string | null; onJudged: (score: CallScore) => void }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const scopes = useOrg().whose?.scopes ?? null;
  const [busy, setBusy] = useState<Busy>("");
  const [sure, setSure] = useState(false);
  const [listed, setListed] = useState(false);
  const [judged, setJudged] = useState(false);
  const [promoted, setPromoted] = useState<Promoted | null>(null);
  const [kept, setKept] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const doing = async (what: Busy, work: () => Promise<void>): Promise<void> => {
    setBusy(what);
    setRefused(null);
    try {
      await work();
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy("");
    }
  };

  // The list is written through `talk` and the judges are asked through `evals`: a key without one is not shown a button it would be refused.
  const mayList = number !== null && number.startsWith("+") && (scopes === null || scopes.includes("talk"));
  const mayJudge = scopes === null || scopes.includes("evals");

  return (
    <section className="calls-part" aria-label="What to do with this call">
      <span className="dash-eyebrow">This call</span>
      <div className="calls-acts">
        {/* Named by the call it came from, so a second keep of the same call is refused by name. */}
        <button type="button" className="app-button" disabled={busy !== "" || agent === "" || kept !== null} title="Goes to the org's Cases, where the nightly plays it" onClick={() => void doing("keep", async () => setKept(await keepCall(credentials, call, `kept-${call.slice(-6).toLowerCase()}`)))}>
          {busy === "keep" ? "Keeping…" : kept !== null ? "Kept as a case" : "Keep as a case"}
        </button>
        <button type="button" className="app-button" disabled={busy !== "" || agent === ""} title="A golden candidate in the agent's test/candidates, in the folder of pinecall start" onClick={() => void doing("promote", async () => setPromoted(await promoteCall(credentials, agent, call)))}>
          {busy === "promote" ? "Writing…" : "Write as a golden"}
        </button>
        {mayJudge && (
          <button
            type="button"
            className="app-button"
            disabled={busy !== ""}
            title="Runs the judges over this call again. It is billed again, as the first judging was."
            onClick={() =>
              void doing("judge", async () => {
                onJudged(await judgeAgain(credentials, call));
                setJudged(true);
              })
            }
          >
            {busy === "judge" ? "Judging…" : "Judge again"}
          </button>
        )}
      </div>
      {judged && <p className="dash-quiet">Judged again. The verdict above is the new one, written on the call's log.</p>}
      {kept !== null && <p className="dash-quiet">Kept as {kept}, in Cases.</p>}
      {promoted !== null && (
        <div className="calls-written">
          <span className="dash-quiet">
            Written down, {promoted.candidate.turns.length} {promoted.candidate.turns.length === 1 ? "turn" : "turns"}
          </span>
          <code className="calls-path">{promoted.path}</code>
          {promoted.notes.map((note) => (
            <span key={note} className="dash-quiet">
              {note}
            </span>
          ))}
        </div>
      )}
      {mayList && (
        <button
          type="button"
          className="calls-link"
          disabled={busy !== "" || listed}
          onClick={() =>
            void doing("list", async () => {
              await optOut(credentials, number);
              setListed(true);
            })
          }
        >
          {busy === "list" ? "Listing…" : listed ? `${number} is on the do-not-call list` : "Do not call this number again"}
        </button>
      )}
      {/* Nothing brings an erased call back: it is asked first, in words. */}
      {sure ? (
        <div className="calls-erase">
          <p className="dash-quiet">Its log, its recording and the memories it taught are erased for good. The audit trail keeps one line saying so.</p>
          <div className="calls-desk-row">
            <button
              type="button"
              className="app-button app-button-danger"
              disabled={busy !== ""}
              onClick={() =>
                void doing("erase", async () => {
                  await eraseCall(credentials, call);
                  void navigate("/calls");
                })
              }
            >
              {busy === "erase" ? "Erasing…" : "Erase for good"}
            </button>
            <button type="button" className="app-button" disabled={busy !== ""} onClick={() => setSure(false)}>
              Keep it
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className="calls-link calls-link-bad" disabled={busy !== ""} onClick={() => setSure(true)}>
          Erase this call
        </button>
      )}
      {refused !== null && <p className="app-refused">{refused}</p>}
    </section>
  );
}
