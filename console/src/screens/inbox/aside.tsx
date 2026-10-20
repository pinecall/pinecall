/** After the call's own panels: the agent's own panel, then who the person is in a sentence, and their conversations a click away. */

import { useEffect, useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago, dayOf, duration } from "../../lib/format";
import { Empty, Item, Pill, Refused } from "../../ui";
import { Drawing } from "./drawn";
import { flagReads, standingOf, type Standing } from "./standing";
import { readDeclaredView, readView, type Drawn } from "./view-door";
import type { Thread } from "./threads";

/**
 * The pane. It is drawn for every agent: the contact's sentence — how often they came, by what,
 * what a reviewer should look at — is folded from the calls the screen already listed, so it costs
 * nothing and is never empty. An agent that declares a view of its own
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
  // The conversations are one click away, so the contact reads as a sentence first.
  const [listing, setListing] = useState(false);
  return (
    <div className="ib-aside" aria-label={`About ${name}`}>
      <TheAgentsOwn agent={agent} contact={thread.contact} call={thread.latest.call} />

      <h3 className="ib-aside-head">Contact</h3>
      <p className="ib-aside-said">{sentenceOf(name, thread, standing)}</p>
      {standing.flags.length > 0 && (
        <div className="ib-aside-flags">
          {standing.flags.map((flag) => (
            <Pill key={flag} tone={flag === "low_score" ? "red" : "amber"} small>
              {flagReads(flag)}
            </Pill>
          ))}
        </div>
      )}
      <button type="button" className="ib-aside-more" aria-expanded={listing} onClick={() => setListing(!listing)}>
        {standing.conversations} {standing.conversations === 1 ? "conversation" : "conversations"}
      </button>
      {listing && (
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
      )}
    </div>
  );
}

/** Who the contact is, in one sentence: their name, how to reach them when that says more, and how often they came. */
function sentenceOf(name: string, thread: Thread, standing: Standing): string {
  const handle = thread.handle !== "web visitor" && thread.handle !== name ? thread.handle : null;
  const visits =
    standing.conversations === 1
      ? "first visit"
      : `${standing.conversations} visits since ${standing.first === null ? "—" : dayOf(standing.first)} · last ${standing.last === null ? "—" : ago(standing.last)}`;
  return [name, handle, visits, standing.channels.join(" and ")].filter((part) => part !== null && part !== "").join(" · ");
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
