/** After the call's own panels: what the console knows about the person, their other conversations, and the agent's own panel. */

import { useEffect, useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago, dayOf, duration } from "../../lib/format";
import { Empty, KV, Item, Pill, Refused, SectionLabel } from "../../ui";
import { Drawing } from "./drawn";
import { flagReads, standingOf } from "./standing";
import { readDeclaredView, readView, type Drawn } from "./view-door";
import type { Thread } from "./threads";

/**
 * The pane. It is drawn for every agent: the standing — how much of this conversation there is,
 * what it came in by, what a reviewer should look at — is folded from the calls the screen already
 * listed, so it costs nothing and is never empty. An agent that declares a view of its own
 * (`@view` on the class) has it drawn above that, from its own systems.
 */
export function Aside({
  agent,
  thread,
  name,
  shown,
  hrefOf,
}: {
  agent: string;
  thread: Thread;
  name: string;
  /** The call on screen, marked in the list of conversations. */
  shown: string;
  /** Where one of the conversations opens: this screen, with that call shown. */
  hrefOf: (call: string) => string;
}): ReactNode {
  const standing = standingOf(thread.lines);
  return (
    <div className="ib-aside" aria-label={`About ${name}`}>
      <TheAgentsOwn agent={agent} contact={thread.contact} call={thread.latest.call} />

      <SectionLabel>Contact</SectionLabel>
      <div className="ib-aside-rows">
        <KV label="Reached by">{standing.channels.join(" · ") || "—"}</KV>
        <KV label="Handle">{thread.handle}</KV>
        <KV label="First seen">{standing.first === null ? "—" : dayOf(standing.first)}</KV>
        <KV label="Last">{standing.last === null ? "—" : ago(standing.last)}</KV>
      </div>

      <SectionLabel ruled>Standing</SectionLabel>
      <div className="ib-aside-facts">
        <Fact value={String(standing.conversations)} label={standing.conversations === 1 ? "conversation" : "conversations"} />
        <Fact value={duration({ started_at: 0, ended_at: standing.seconds })} label="on the line" />
        {standing.judged > 0 && <Fact value={`${String(standing.held)}/${String(standing.judged)}`} label="judges held" />}
      </div>
      {standing.flags.length > 0 && (
        <div className="ib-aside-flags">
          {standing.flags.map((flag) => (
            <Pill key={flag} tone={flag === "low_score" ? "red" : "amber"} small>
              {flagReads(flag)}
            </Pill>
          ))}
        </div>
      )}

      <SectionLabel ruled>Conversations</SectionLabel>
      <div className="ib-aside-list">
        {thread.lines.map((line) => (
          <Item
            key={line.call}
            name={
              <span className={line.call === shown ? "ib-aside-shown" : undefined}>
                {line.started_at === null ? line.call : dayOf(line.started_at)}
                {line.call === shown && " · shown"}
              </span>
            }
            sub={`${line.channel ?? "—"} · ${line.status === "ended" ? duration(line) : "on the line now"}`}
            end={line.outcome !== null && line.outcome !== "" ? <span className="ib-aside-outcome">{line.outcome}</span> : undefined}
            to={hrefOf(line.call)}
          />
        ))}
      </div>
    </div>
  );
}

function Fact({ value, label }: { value: string; label: string }): ReactNode {
  return (
    <div className="ib-panel-stat">
      <span className="ib-panel-stat-value">{value}</span>
      <span className="ib-panel-stat-label">{label}</span>
    </div>
  );
}

/**
 * The agent's own panel, if it draws one. Asked of the app holding the agent, per conversation,
 * so a thread opened from the list asks once and an agent that declares no view asks nothing at
 * all — the pane is then the console's own facts, which is what every agent had before.
 */
function TheAgentsOwn({ agent, contact, call }: { agent: string; contact: string; call: string }): ReactNode {
  const credentials = useCredentials();
  const [declared, setDeclared] = useState<string | null>(null);
  const [drawn, setDrawn] = useState<Drawn | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);

  useEffect(() => {
    let gone = false;
    readDeclaredView(credentials, agent).then(
      (name) => {
        if (!gone) setDeclared(name);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  useEffect(() => {
    if (declared === null) return;
    let gone = false;
    setDrawing(true);
    setRefused(null);
    readView(credentials, agent, contact, call).then(
      (panel) => {
        if (gone) return;
        setDrawn(panel);
        setDrawing(false);
      },
      (failed: unknown) => {
        if (gone) return;
        // The app's own refusal, word for word: a view that threw says why, in the pane, and the
        // facts under it are still read.
        setRefused(failed instanceof GatewayError ? failed.message : String(failed));
        setDrawing(false);
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, contact, call, declared]);

  if (declared === null) return null;
  return (
    <div className="ib-aside-own">
      {drawing && drawn === null && refused === null && <Empty>Drawing {declared}…</Empty>}
      <Refused>{refused}</Refused>
      {drawn !== null && drawn.nodes.length === 0 && <Empty>{declared} has nothing for this conversation.</Empty>}
      {drawn !== null && <Drawing nodes={drawn.nodes} />}
    </div>
  );
}
