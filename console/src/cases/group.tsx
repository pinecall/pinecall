/** One group of cases: the cause its calls share, the fix its diagnosis names with the one move that makes it, and the calls themselves, each opening beside the list. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago, percent } from "../lib/format";
import { saidIn } from "../test/fold";
import { applyGroup, callerFromGroup, decideGroup, diagnoseGroup, type CaseGroup, type EvalCase, type Proposal } from "./door";

// How many of a group's calls are drawn before the rest fold.
const A_FEW = 4;

const KIND: Record<Proposal["kind"], string> = { setting: "A setting", code: "The code", knowledge: "The knowledge", none: "Nothing to fix" };

function changeOf(proposal: Proposal): string {
  return typeof proposal.change === "string" ? proposal.change : (JSON.stringify(proposal.change, null, 2) ?? "");
}

/** What an assistant holding the pinecall MCP is told to do with the group. */
function promptFor(group: CaseGroup, proposal: Proposal): string {
  return `Pinecall case group ${group.id} (judge ${group.judge}): ${proposal.cause}\nProposed ${proposal.kind} fix at ${proposal.where}: ${changeOf(proposal)}\nUse the pinecall MCP's cases tool: group ${group.id}, make the change, run test with case until it holds, then approve the group.`;
}

/** Where a case came from, in a few words. */
export function fromOf(kept: EvalCase): string {
  if (kept.source === "person") return "Written by a person";
  if (kept.source === "simulation") return `Simulated${kept.persona ? ` by ${kept.persona}` : ""}`;
  return kept.source_call === null ? "Kept by a person" : "A real call";
}

export function CaseRow({ kept, everyAgent, on, onOpen }: { kept: EvalCase; everyAgent: boolean; on: boolean; onOpen: () => void }): ReactNode {
  return (
    <button type="button" className={on ? "dash-row cs-row cs-row-on" : "dash-row cs-row"} aria-pressed={on} onClick={onOpen}>
      <span className="cs-row-main">
        <span className="cs-row-said dash-clip">{saidIn(kept.golden)[0] ?? kept.name}</span>
        <span className="cs-row-under dash-clip">
          {kept.name}
          {kept.held_out && " · held out"}
        </span>
      </span>
      <span className="cs-row-from dash-clip">
        {everyAgent ? `${kept.agent} · ` : ""}
        {fromOf(kept)}
      </span>
      <span className="cs-row-when">{ago(kept.created_at)}</span>
    </button>
  );
}

function Diagnosis({ group, proposal }: { group: CaseGroup; proposal: Proposal }): ReactNode {
  if (proposal.kind === "none") {
    return (
      <div className="cs-fix">
        <span className="cs-fix-top">
          <span className="dash-eyebrow">Diagnosis</span>
          <span className="dash-quiet">{percent(proposal.confidence)} sure</span>
        </span>
        <p className="cs-fix-cause">{proposal.cause}</p>
        <p className="dash-quiet">No fault of the agent's. If {group.judge} should have held, dismiss the group and say the judge was wrong: that is what calibrates it.</p>
      </div>
    );
  }
  return (
    <div className="cs-fix">
      <span className="cs-fix-top">
        <span className="dash-eyebrow">Suggested fix</span>
        <span className="dash-quiet">{percent(proposal.confidence)} sure</span>
      </span>
      <p className="cs-fix-cause">{proposal.cause}</p>
      <div className="cs-fix-where">
        <span className="dash-tag">{KIND[proposal.kind]}</span>
        <span className="cs-fix-at">{proposal.where}</span>
      </div>
      <pre className="cs-fix-change">{changeOf(proposal)}</pre>
    </div>
  );
}

export function Group({ group, cases, everyAgent, open, onOpen, onChanged }: { group: CaseGroup; /** The cases of this group among those read. */ cases: readonly EvalCase[]; everyAgent: boolean; /** The id of the case open beside the list. */ open: string | null; onOpen: (kept: EvalCase) => void; /** The group as a door answered it. */ onChanged: (group: CaseGroup) => void }): ReactNode {
  const credentials = useCredentials();
  const [busy, setBusy] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState(false);
  const [all, setAll] = useState(false);
  const proposal = group.proposal ?? null;
  const pending = group.status === "pending";

  const run = async (what: string, doing: () => Promise<string | CaseGroup>): Promise<void> => {
    if (busy !== null) return;
    setBusy(what);
    setRefused(null);
    setSaid(null);
    try {
      const done = await doing();
      if (typeof done === "string") setSaid(done);
      else onChanged(done);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(null);
    }
  };
  const diagnose = (): void => void run("diagnose", () => diagnoseGroup(credentials, group.id));
  const approve = (): void => void run("approve", () => decideGroup(credentials, group.id, { status: "approved" }));
  const dismiss = (wrong: boolean): void => void run("dismiss", () => decideGroup(credentials, group.id, wrong ? { status: "dismissed", judge_was_wrong: true } : { status: "dismissed" }));
  const apply = (): void =>
    void run("apply", async () => {
      await applyGroup(credentials, group.id);
      return "Applied as a new version of your own settings. Open a call below and run it on that version; once it holds, approve the group.";
    });
  const copy = (): void =>
    void run("copy", async () => {
      if (proposal !== null) await navigator.clipboard.writeText(promptFor(group, proposal));
      return "Copied. Paste it to your assistant, which has the pinecall MCP.";
    });
  const caller = (): void =>
    void run("caller", async () => {
      await callerFromGroup(credentials, group.id);
      return "A caller like these is now one of the agent's own. Simulations has it.";
    });

  const shown = all ? cases : cases.slice(0, A_FEW);
  return (
    <section className="dash-card cs-group" aria-label={group.cause}>
      <div className="cs-group-top">
        <div className="cs-group-words">
          <h2 className="cs-cause">{group.cause}</h2>
          <p className="cs-meta">
            <Link to={`/judges?judge=${encodeURIComponent(group.judge)}`} className="cs-judge">
              {group.judge}
            </Link>
            <span>
              {group.cases} {group.cases === 1 ? "call" : "calls"}
              {group.simulations > 0 && `, ${group.simulations} simulated`}
            </span>
            {everyAgent && <span>{group.agent}</span>}
            <span>Since {ago(group.since)}</span>
          </p>
        </div>
        {pending && (
          <div className="cs-moves">
            {proposal === null && (
              <button type="button" className="cfg-save" disabled={busy !== null} onClick={diagnose}>
                {busy === "diagnose" ? "Diagnosing…" : "Diagnose"}
              </button>
            )}
            {proposal?.kind === "setting" && (
              <button type="button" className="cfg-save" disabled={busy !== null} onClick={apply}>
                {busy === "apply" ? "Applying…" : "Apply the setting"}
              </button>
            )}
            {proposal?.kind === "code" && (
              <button type="button" className="cfg-save" disabled={busy !== null} onClick={copy}>
                Copy for your assistant
              </button>
            )}
            <button type="button" className="app-button" disabled={busy !== null} title="Every call of the group becomes a golden, played on each run" onClick={approve}>
              {busy === "approve" ? "Approving…" : "Approve all"}
            </button>
            <button type="button" className="app-button" aria-expanded={dismissing} disabled={busy !== null} onClick={() => setDismissing(!dismissing)}>
              Dismiss
            </button>
          </div>
        )}
      </div>

      {dismissing && pending && (
        <div className="cs-dismiss">
          <span className="dash-quiet">Why? It is what the judge learns from.</span>
          <button type="button" className="app-button" disabled={busy !== null} onClick={() => dismiss(true)}>
            {group.judge} was wrong, the agent did fine
          </button>
          <button type="button" className="app-button" disabled={busy !== null} onClick={() => dismiss(false)}>
            Not worth keeping
          </button>
        </div>
      )}

      {proposal !== null && <Diagnosis group={group} proposal={proposal} />}
      {said !== null && <p className="cs-said">{said}</p>}
      {refused !== null && <p className="app-refused">{refused}</p>}

      <div className="dash-rows cs-rows">
        {shown.map((kept) => (
          <CaseRow key={kept.id} kept={kept} everyAgent={false} on={kept.id === open} onOpen={() => onOpen(kept)} />
        ))}
      </div>
      {cases.length === 0 && <p className="dash-quiet">Its calls are not among the newest read.</p>}

      {(cases.length > A_FEW || pending) && (
        <div className="cs-foot">
          {cases.length > A_FEW && (
            <button type="button" className="cs-link" onClick={() => setAll(!all)}>
              {all ? "Show fewer" : `Show all ${cases.length}`}
            </button>
          )}
          {pending && proposal !== null && (
            <button type="button" className="cs-link" disabled={busy !== null} onClick={diagnose}>
              {busy === "diagnose" ? "Diagnosing…" : "Diagnose again"}
            </button>
          )}
          {pending && (
            <button type="button" className="cs-link" disabled={busy !== null} title="A simulated caller written from the newest of these calls" onClick={caller}>
              {busy === "caller" ? "Writing…" : "Make a caller like these"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
