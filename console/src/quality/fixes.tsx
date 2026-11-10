/** Suggested fixes: the case groups waiting whose diagnosis names a change, with what each fixes, where it lands, and the one move that makes it. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { applyGroup, type CaseGroup, type Proposal } from "./door";

/** A group a fix is ready for: waiting, diagnosed, and the diagnosis is the agent's to change. */
export function fixable(group: CaseGroup): boolean {
  return group.status === "pending" && group.proposal !== null && group.proposal !== undefined && group.proposal.kind !== "none";
}

// Where each kind of fix lands, said under it.
const LANDS: Record<string, (where: string) => string> = {
  setting: (where) => `Changes ${where} in the agent's settings`,
  code: (where) => `A change in ${where}, made by your assistant`,
  knowledge: (where) => `Adds to ${where}`,
};

/** What an assistant holding the pinecall MCP is told to do with the group. */
function promptFor(group: CaseGroup, proposal: Proposal): string {
  return `Pinecall case group ${group.id} (judge ${group.judge}): ${proposal.cause}\nProposed ${proposal.kind} fix at ${proposal.where}: ${typeof proposal.change === "string" ? proposal.change : JSON.stringify(proposal.change)}\nUse the pinecall MCP's cases tool: group ${group.id}, make the change, run test with case until it holds, then approve the group.`;
}

function Fix({ group, everyAgent }: { group: CaseGroup; everyAgent: boolean }): ReactNode {
  const credentials = useCredentials();
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const proposal = group.proposal;
  if (proposal === null || proposal === undefined) return null;

  const does = async (doing: () => Promise<string>): Promise<void> => {
    setBusy(true);
    setRefused(null);
    try {
      setSaid(await doing());
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };
  const apply = (): void =>
    void does(async () => {
      await applyGroup(credentials, group.id);
      return "Applied as a new version of the agent's settings.";
    });
  const copy = (): void =>
    void does(async () => {
      await navigator.clipboard.writeText(promptFor(group, proposal));
      return "Copied. Paste it to your assistant, which has the pinecall MCP.";
    });

  return (
    <div className="dash-part ql-fix">
      <p className="ql-fix-title">{proposal.cause}</p>
      <p className="dash-quiet">
        Fixes {group.cases} {group.cases === 1 ? "call" : "calls"}
        {everyAgent ? ` of ${group.agent}` : ""} that {group.judge} broke: {group.cause}
      </p>
      {said !== null && <p className="ql-said">{said}</p>}
      {refused !== null && <p className="app-refused">{refused}</p>}
      <div className="ql-fix-foot">
        <span className="dash-quiet ql-fix-where">{(LANDS[proposal.kind] ?? ((where: string) => where))(proposal.where)}</span>
        {/* A setting is applied here and code goes to the assistant; knowledge is added where the base is kept. */}
        {proposal.kind === "setting" && (
          <button type="button" className="ql-solid" disabled={busy || said !== null} onClick={apply}>
            {busy ? "Applying…" : said !== null ? "Applied" : "Apply"}
          </button>
        )}
        {proposal.kind === "code" && (
          <button type="button" className="ql-solid" disabled={busy} onClick={copy}>
            Copy for your assistant
          </button>
        )}
      </div>
    </div>
  );
}

export function Fixes({ groups, everyAgent }: { groups: readonly CaseGroup[]; everyAgent: boolean }): ReactNode {
  if (groups.length === 0) return null;
  return (
    <section className="dash-card" aria-label="Suggested fixes">
      <div className="dash-card-top ql-card-top">
        <span className="dash-eyebrow">Suggested fixes</span>
        <span className="dash-quiet dash-clip">Written from the calls that broke</span>
      </div>
      <div className="ql-fixes">
        {groups.map((group) => (
          <Fix key={group.id} group={group} everyAgent={everyAgent} />
        ))}
      </div>
    </section>
  );
}
