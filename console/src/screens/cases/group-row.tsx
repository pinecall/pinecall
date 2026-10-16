/** One group of cases: what broke, in a line, with the one move that fits it — the rest, and the calls themselves, behind a click. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../../lib/format";
import { ownedAt } from "../../lib/harness";
import { Button, ButtonLink, Pill, TextAction } from "../../ui";
import { Creature } from "../quality/creature";
import { applyGroup, decideGroup, personaFromGroup, proposeGroup, type CaseGroup, type EvalCase, type Proposal } from "./door";

const STATUS_TONE = { pending: "amber", approved: "green", dismissed: "gray" } as const;

/** What the assistant is told for a code fix: the MCP's `cases` tool knows the rest. */
function promptFor(group: CaseGroup, proposal: Proposal): string {
  return `Pinecall case group ${group.id} (judge ${group.judge}): ${proposal.cause}\nProposed ${proposal.kind} fix at ${proposal.where}: ${typeof proposal.change === "string" ? proposal.change : JSON.stringify(proposal.change)}\nUse the pinecall MCP's cases tool: group ${group.id}, make the change, run test with case until it holds, then approve the group.`;
}

export function GroupRow({
  agent,
  group,
  calls,
  onGrouped,
}: {
  /** The agent in view, or "" for every agent. */
  agent: string;
  group: CaseGroup;
  /** The cases of this group the page has read, to open from it. */
  calls: EvalCase[];
  onGrouped: (group: CaseGroup) => void;
}): ReactNode {
  const credentials = useCredentials();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
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
      else onGrouped(done);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(null);
    }
  };
  const copied = async (): Promise<string> => {
    if (proposal === null) return "";
    await navigator.clipboard.writeText(promptFor(group, proposal));
    return "Copied: paste it to your assistant, which has the pinecall MCP.";
  };
  const apply = async (): Promise<string> => {
    await applyGroup(credentials, group.id);
    return "Applied as a new version of your settings: run the group's cases on it.";
  };
  const persona = async (): Promise<string> => {
    await personaFromGroup(credentials, group.id);
    return "A persona like these callers is kept as the agent's own: Personas has it.";
  };

  // The one move that fits where the group stands: read it, then the fix its diagnosis names.
  const primary = ((): ReactNode => {
    if (!pending) return null;
    if (proposal === null) {
      return (
        <Button size="sm" kind="primary" disabled={busy !== null} onClick={() => void run("propose", () => proposeGroup(credentials, group.id))}>
          {busy === "propose" ? "Diagnosing…" : "Diagnose"}
        </Button>
      );
    }
    if (proposal.kind === "setting") {
      return (
        <Button size="sm" kind="primary" disabled={busy !== null} onClick={() => void run("apply", apply)}>
          {busy === "apply" ? "Applying…" : "Apply the setting"}
        </Button>
      );
    }
    if (proposal.kind === "code") {
      return (
        <Button size="sm" kind="primary" disabled={busy !== null} onClick={() => void run("copy", copied)}>
          Open in your assistant
        </Button>
      );
    }
    return (
      <Button size="sm" disabled={busy !== null} onClick={() => void run("approve", () => decideGroup(credentials, group.id, { status: "approved" }))}>
        Approve all
      </Button>
    );
  })();

  return (
    <li className="cs-g">
      <Creature name={group.judge} size={40} />
      <div className="cs-g-body">
        <p className="cs-g-cause">{group.cause}</p>
        <p className="cs-g-meta">
          <b>{group.judge}</b>
          <span>
            {group.cases} call{group.cases === 1 ? "" : "s"}
            {group.simulations > 0 && ` · ${group.simulations} simulated`}
          </span>
          {agent === "" && <span>{group.agent}</span>}
          <span>{ago(group.since)}</span>
          {!pending && (
            <Pill tone={STATUS_TONE[group.status]} small>
              {group.status}
            </Pill>
          )}
        </p>
        {proposal !== null && (
          <p className="cs-g-fix">
            {proposal.kind === "none" ? "No fault of the agent's." : `Fix · ${proposal.kind} · ${proposal.where} — ${typeof proposal.change === "string" ? proposal.change : JSON.stringify(proposal.change)}`}
            <span> · {Math.round(proposal.confidence * 100)}% sure</span>
          </p>
        )}
        {said !== null && <p className="cs-g-said">{said}</p>}
        {refused !== null && <p className="cs-bad">{refused}</p>}
        {open && (
          <div className="cs-g-more">
            {pending && (
              <div className="cs-g-moves">
                {proposal !== null && (
                  <Button size="sm" disabled={busy !== null} onClick={() => void run("propose", () => proposeGroup(credentials, group.id))}>
                    Diagnose again
                  </Button>
                )}
                {proposal?.kind === "setting" && (
                  <ButtonLink size="sm" to={`/a/${encodeURIComponent(group.agent)}/configure`}>
                    Open Configure
                  </ButtonLink>
                )}
                <Button size="sm" disabled={busy !== null} onClick={() => void run("persona", persona)}>
                  {busy === "persona" ? "Writing…" : "Make a persona"}
                </Button>
                <Button size="sm" disabled={busy !== null} onClick={() => void run("approve", () => decideGroup(credentials, group.id, { status: "approved" }))}>
                  Approve all
                </Button>
                <Button size="sm" disabled={busy !== null} onClick={() => void run("wrong", () => decideGroup(credentials, group.id, { status: "dismissed", judge_was_wrong: true }))}>
                  {group.judge} was wrong
                </Button>
                <Button size="sm" disabled={busy !== null} onClick={() => void run("dismiss", () => decideGroup(credentials, group.id, { status: "dismissed" }))}>
                  Dismiss all
                </Button>
              </div>
            )}
            <ul className="cs-g-calls">
              {calls.map((kept) => (
                <li key={kept.id}>
                  <Link to={ownedAt(agent, "cases", kept.agent, kept.name)}>
                    <span className="cs-g-said-line">{kept.golden.turns?.find((turn) => turn.say !== undefined && turn.say !== null)?.say ?? kept.name}</span>
                    <span className="cs-g-from">
                      {kept.source === "simulation" ? `simulated${kept.persona ? ` by ${kept.persona}` : ""}` : "a real call"} · {ago(kept.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
              {calls.length === 0 && <li className="cs-g-from">The calls of this group are not among the newest read.</li>}
            </ul>
          </div>
        )}
      </div>
      <div className="cs-g-side">
        {primary}
        <TextAction onClick={() => setOpen(!open)}>{open ? "Less" : "More"}</TextAction>
      </div>
    </li>
  );
}
