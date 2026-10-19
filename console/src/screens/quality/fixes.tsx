/** Suggested fixes: the case groups waiting whose diagnosis names a change — what it fixes, where it lands, and the one move that makes it. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { rowAt } from "../../lib/harness";
import { Button, ButtonLink, Icon } from "../../ui";
import { applyGroup, promptFor, type CaseGroup } from "../cases";

/** A group a fix is ready for: pending, diagnosed, and the diagnosis is the agent's to change. */
export function fixable(group: CaseGroup): boolean {
  return group.status === "pending" && group.proposal !== null && group.proposal !== undefined && group.proposal.kind !== "none";
}

// Where each kind of fix lands, said under it.
const LANDS: Record<string, (where: string) => string> = {
  setting: (where) => `Changes ${where} in Configure`,
  code: (where) => `A change in ${where}, made by your assistant`,
  knowledge: (where) => `Adds to ${where}`,
};

export function Fixes({ groups, agent }: { groups: readonly CaseGroup[]; agent: string }): ReactNode {
  if (groups.length === 0) return null;
  return (
    <section className="qly-fixes" aria-label="Suggested fixes">
      <div className="qly-fixes-head">
        <span className="qly-fixes-icon" aria-hidden>
          <Icon name="bulb" size={17} />
        </span>
        <span className="qly-fixes-title">Suggested fixes</span>
        <span className="qly-fixes-meta">written from the calls that broke</span>
      </div>
      <div className="qly-fixes-row">
        {groups.map((group) => (
          <Fix key={group.id} group={group} agent={agent} />
        ))}
      </div>
    </section>
  );
}

function Fix({ group, agent }: { group: CaseGroup; agent: string }): ReactNode {
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

  // The move that fits the kind: a setting is applied here, code goes to the assistant, knowledge is Cases' to read.
  const move =
    proposal.kind === "setting" ? (
      <Button
        kind="primary"
        size="sm"
        disabled={busy || said !== null}
        onClick={() =>
          void does(async () => {
            await applyGroup(credentials, group.id);
            return "Applied as a new version of your settings.";
          })
        }
      >
        {busy ? "Applying…" : said !== null ? "Applied" : "Apply"}
      </Button>
    ) : proposal.kind === "code" ? (
      <Button
        kind="primary"
        size="sm"
        disabled={busy}
        onClick={() =>
          void does(async () => {
            await navigator.clipboard.writeText(promptFor(group, proposal));
            return "Copied: paste it to your assistant, which has the pinecall MCP.";
          })
        }
      >
        Copy for your assistant
      </Button>
    ) : (
      <ButtonLink kind="primary" size="sm" to={rowAt(agent, "cases")}>
        Open in Cases
      </ButtonLink>
    );

  return (
    <div className="qly-fix">
      <p className="qly-fix-title">{proposal.cause}</p>
      <p className="qly-fix-what">
        Fixes {group.cases} {group.cases === 1 ? "call" : "calls"}
        {agent === "" ? ` on ${group.agent}` : ""} that {group.judge} broke: {group.cause}
      </p>
      {said !== null && <p className="qly-fix-said">{said}</p>}
      {refused !== null && <p className="qly-fix-bad">{refused}</p>}
      <div className="qly-fix-foot">
        <span className="qly-fix-where">{(LANDS[proposal.kind] ?? ((where: string) => where))(proposal.where)}</span>
        {move}
      </div>
    </div>
  );
}
