/** Calls read as threads: the conversations as a messenger shows them — one thread per person — beside the one open, drawn the one way a call is. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate, useParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { wantsAPerson } from "@pinecall/core/calls";
import { clockOf, dayOf, today, utcDay } from "../../lib/format";
import { useOrg } from "../../lib/org";
import { Avatar, usePane } from "../../ui";
import { Call } from "../call";
import type { Outbound } from "../numbers/door";
import { Aside } from "./aside";
import { CallBack, DialForm, useOutbound } from "./dial";
import { markRead, readDoorThreads, writeTo, type DoorThread } from "./inbox-door";
import { lastOf, lettersOf, threadsOf, titleOf, type Thread } from "./threads";
import "./inbox.css";

/**
 * Calls read as threads. The threads are the calls Calls hands it — the org's, or the agent in
 * view's, through the status picked — grouped by who was on them: a contact who talked to two
 * agents is ONE thread, and its agent is whoever took the newest call. The URL names a call, and
 * the thread holding it is the one open: THE CALL, drawn exactly one way — the chat, the transcript
 * with every tool call, or the log; the desk on a live one, which is where a supervisor works; its
 * verdict on one that is over — with the person after the call's own panels, and their other
 * conversations there, each one click from being the call shown. In focus the list folds away and
 * the call has the screen. What the gateway keeps per contact on top of that — names, what is
 * unread, a call back, writing into a closed thread — is per agent, so it is drawn with one agent
 * in view and only then.
 */
export function Inbox({ listed, focus, onFocus }: { listed: readonly SessionLine[]; focus: boolean; onFocus: () => void }): ReactNode {
  const params = useParams();
  const agent = params["agent"] ?? "";
  const chosen = params["call"];
  const navigate = useNavigate();
  const { search } = useLocation();
  const credentials = useCredentials();
  const { floorError } = useOrg();
  const threads = useMemo(() => threadsOf(listed), [listed]);
  const [query, setQuery] = useState("");
  const pane = usePane({ name: "agent.conversations", initial: 292, min: 200, max: 520, side: "left" });
  const [dialling, setDialling] = useState(false);
  const outbound = useOutbound();
  const [door, seen] = useDoorThreads(agent, listed.length);
  const [refused, setRefused] = useState<string | null>(null);

  const open = threads.find((thread) => chosen !== undefined && thread.lines.some((line) => line.call === chosen)) ?? threads[0];
  // The call on screen where the screen opens a call: the one the URL names, else the thread's newest.
  const call = open === undefined ? undefined : (open.lines.find((line) => line.call === chosen) ?? open.latest);
  const base = agent === "" ? "/calls" : `/a/${encodeURIComponent(agent)}/calls`;
  // The status picked and the focus ride along: opening another conversation keeps the list as it is.
  const hrefOf = (one: string): string => `${base}/${one}${search}`;
  const words = query.trim().toLowerCase();
  const shown = threads.filter((thread) => words === "" || `${nameOf(thread, door)} ${thread.handle} ${lastOf(thread)}`.toLowerCase().includes(words));

  // The thread open is read the moment it is open, by a click or by the URL: its mark goes at once,
  // and the gateway is told for this reader's next visit.
  useEffect(() => {
    if (open === undefined || door === null || (door.get(open.contact)?.unread ?? 0) === 0) return;
    seen(open.contact);
    void markRead(credentials, agent, open.contact).catch(() => undefined);
  }, [open?.contact, door, credentials, agent, seen]);

  // Whose thread this is: the agent of its newest call, which on the agent's own tab is that agent.
  const whose = open?.latest.agent ?? agent;

  return (
    <div className={focus ? "ib ib-focus" : "ib"} style={pane.style}>
      {!focus && pane.handle}
      <div className="ib-list">
        <div className="ib-list-head">
          <input className="ib-search" placeholder="Search a caller or number" value={query} onChange={(event) => setQuery(event.target.value)} />
          {/* Simulating a caller is the Simulations screen's; here the + calls a real number as ONE
              agent, so it is drawn where the path names one. */}
          {outbound !== null && agent !== "" && (
            <button type="button" className="ib-call" title="Call a number" aria-expanded={dialling} onClick={() => setDialling(!dialling)}>
              +
            </button>
          )}
          {dialling && outbound !== null && agent !== "" && (
            <div className="ib-dial">
              <div className="dial-panel">
                <div className="dial-panel-head">
                  <span className="dial-panel-title">Call a number</span>
                  <button type="button" className="dial-panel-close" onClick={() => setDialling(false)} aria-label="close">
                    ×
                  </button>
                </div>
                <DialForm agent={agent} outbound={outbound} onClose={() => setDialling(false)} />
              </div>
            </div>
          )}
        </div>
        <div className="ib-threads">
          {floorError !== null && <p className="ib-empty ib-refused">{floorError}</p>}
          {floorError === null && threads.length === 0 && (
            <p className="ib-empty">No conversations yet. The first call to reach {agent === "" ? "an agent" : agent} opens a thread here as it rings.</p>
          )}
          {threads.length > 0 && shown.length === 0 && <p className="ib-empty">Nobody here matches “{query}”.</p>}
          {shown.map((thread) => (
            <ThreadRow
              key={thread.contact}
              thread={thread}
              name={nameOf(thread, door)}
              whose={agent === "" ? thread.latest.agent : undefined}
              fresh={(door?.get(thread.contact)?.unread ?? 0) > 0}
              on={thread === open}
              onOpen={() => void navigate(hrefOf(thread.latest.call))}
            />
          ))}
        </div>
      </div>
      {open === undefined || call === undefined ? (
        <div className="ib-open">
          <p className="ib-nothing">{floorError === null ? "Pick a conversation on the left." : ""}</p>
        </div>
      ) : (
        <div className="ib-open">
          {refused !== null && <p className="ib-refused-line ib-refused-head">{refused}</p>}
          {/* The call, one hook and one stream, drawn the one way a call is. Around it what is the
              thread's: its name and moves in the head, writing into a closed WhatsApp thread under
              the log, the person and their other conversations after the call's panels. */}
          <Call
            key={call.call}
            call={call.call}
            agent={whose}
            name={nameOf(open, door)}
            beside={() => <ThreadMoves agent={whose} thread={open} outbound={outbound} focus={focus} onFocus={onFocus} onRefused={setRefused} />}
            foot={door !== null && call.status === "ended" && call.channel === "whatsapp" ? <Composer agent={whose} contact={open.contact} /> : undefined}
            aside={<Aside key={`${open.contact}-aside`} agent={whose} thread={open} name={nameOf(open, door)} shown={call.call} hrefOf={hrefOf} />}
          />
        </div>
      )}
    </div>
  );
}

function nameOf(thread: Thread, door: Map<string, DoorThread> | null): string {
  return door?.get(thread.contact)?.name ?? titleOf(thread);
}

// Asked once per agent and again when the calls it lists change; a gateway without the door answers
// 404 once and is not asked again on this screen. The door is one agent's, so the org's inbox asks
// nothing and names a thread the way its own log does — a name written down for one agent is not
// the org's name for that person.
function useDoorThreads(agent: string, moved: number): [Map<string, DoorThread> | null, (contact: string) => void] {
  const credentials = useCredentials();
  const [threads, setThreads] = useState<Map<string, DoorThread> | null>(null);
  // A thread opened is read here at once; the next read of the door says the same, from the gateway.
  const seen = useCallback((contact: string) => {
    setThreads((held) => {
      const thread = held?.get(contact);
      if (held === null || thread === undefined || (thread.unread ?? 0) === 0) return held;
      return new Map(held).set(contact, { ...thread, unread: 0 });
    });
  }, []);
  const [absent, setAbsent] = useState(false);
  useEffect(() => {
    if (absent || agent === "") return;
    let gone = false;
    readDoorThreads(credentials, agent).then(
      (read) => {
        if (gone) return;
        if (read === null) setAbsent(true);
        setThreads(read);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, moved, absent]);
  return [threads, seen];
}

function ThreadRow({
  thread,
  name,
  whose,
  fresh,
  on,
  onOpen,
}: {
  thread: Thread;
  name: string;
  /** The agent of its newest call, on the org's list where threads of every agent sit together. */
  whose: string | undefined;
  /** Something came in on it this reader has not opened yet. */
  fresh: boolean;
  on: boolean;
  onOpen: () => void;
}): ReactNode {
  return (
    <button type="button" className={on ? "ib-row ib-row-on" : "ib-row"} onClick={onOpen}>
      <Avatar name={name} letters={lettersOf(thread)} size={28} round />
      <span className="ib-row-main">
        <span className="ib-row-top">
          <span className="ib-row-name">{name}</span>
          <span className="ib-row-time">{whenOf(thread.latest.started_at)}</span>
        </span>
        <span className="ib-row-bottom">
          {/* A contact the agent asked a person for is waiting on somebody in this list. */}
          {wantsAPerson(thread.latest) ? (
            <span className="ib-row-last ib-row-asked">wants a person</span>
          ) : (
            <span className={thread.latest.status !== "ended" ? "ib-row-last ib-row-last-live" : "ib-row-last"}>{lastOf(thread)}</span>
          )}
          {/* One thing at the end, the one that matters: live, new, a judge that broke — else whose it is. */}
          {markOf(thread.latest, fresh) ?? (whose !== undefined && <span className="ib-row-agent">{whose}</span>)}
        </span>
      </span>
    </button>
  );
}

/** The row's mark, when there is one worth it: live, new, or a verdict that broke. A call that held says nothing. */
function markOf(line: Thread["latest"], fresh: boolean): ReactNode | null {
  if (line.status !== "ended") return <span className={wantsAPerson(line) ? "ib-mark ib-mark-live ib-mark-asked" : "ib-mark ib-mark-live"} aria-label="live" />;
  // New, not how many: the door counts calls and lines, which is not what a reader means by messages.
  if (fresh) return <span className="ib-new" aria-label="new" />;
  const score = line.score;
  if (score === null || score === undefined || score.judged === 0 || score.passed) return null;
  return (
    <span className="ib-mark ib-mark-broke">
      {score.held}/{score.judged}
    </span>
  );
}

// `13:24` today, `Yesterday`, then the day.
function whenOf(at: number | null): string {
  if (at === null) return "";
  const days = today();
  const day = utcDay(at);
  if (day === days.today) return clockOf(at).slice(0, 5);
  if (day === days.yesterday) return "Yesterday";
  return dayOf(at);
}

/** The thread's moves in the call's head: the conversation alone on the screen, and a call back to a phone number. */
function ThreadMoves({
  agent,
  thread,
  outbound,
  focus,
  onFocus,
  onRefused,
}: {
  agent: string;
  thread: Thread;
  outbound: Outbound | null;
  focus: boolean;
  onFocus: () => void;
  onRefused: (why: string | null) => void;
}): ReactNode {
  const [calling, setCalling] = useState(false);
  const closeCalling = useCallback(() => setCalling(false), []);
  // A call BACK: to a phone number, and only once the org can place a call at all.
  const phone = outbound !== null && thread.contact.startsWith("+");
  return (
    <>
      <button type="button" className="ui-button ui-button-sm" onClick={onFocus} title={focus ? "Show the conversations beside the call" : "Give the call the whole screen"}>
        {focus ? "Show the list" : "Focus"}
      </button>
      {phone && outbound !== null && (
        <span className="dial-anchor">
          <button type="button" className="ui-button ui-button-primary ui-button-sm" aria-expanded={calling} onClick={() => setCalling(!calling)}>
            Call back
          </button>
          {calling && <CallBack agent={agent} to={thread.contact} outbound={outbound} onClose={closeCalling} onRefused={onRefused} />}
        </span>
      )}
    </>
  );
}

// Into a live call a person speaks from the desk, which has Say. This is the other way to write:
// as the agent, into a closed WhatsApp thread, through the gateway's own door and inside the
// channel's window — the one thing a messenger does that a call's page has no place for.
function Composer({ agent, contact }: { agent: string; contact: string }): ReactNode {
  const credentials = useCredentials();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const send = async (): Promise<void> => {
    if (text.trim() === "") return;
    setSending(true);
    setRefused(null);
    try {
      await writeTo(credentials, agent, contact, text.trim());
      setText("");
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      {refused !== null && <p className="ib-refused-line ib-refused-foot">{refused}</p>}
      <form
        className="ib-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <input className="ib-write" value={text} placeholder={`Write as ${agent} — the agent keeps the thread from here`} disabled={sending} onChange={(event) => setText(event.target.value)} />
        <button type="submit" className="ib-send" disabled={sending || text.trim() === ""}>
          Send
        </button>
      </form>
    </>
  );
}
