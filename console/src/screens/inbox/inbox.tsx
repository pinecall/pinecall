/** Calls read as threads: the conversations as a messenger shows them — one thread per person — beside the one open, drawn the one way a call is. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import { Fragment, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate, useParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { elapsed, isLive, wantsAPerson, type CallDay } from "@pinecall/core/calls";
import { clockOf, dayOf } from "../../lib/format";
import { useOrg } from "../../lib/org";
import { Avatar, Icon, Pill, usePane } from "../../ui";
import { Call } from "../call";
import type { Outbound } from "../numbers/door";
import { Aside } from "./aside";
import { CallBack, DialForm, useOutbound } from "./dial";
import { markRead, readDoorThreads, writeTo, type DoorThread } from "./inbox-door";
import { lastOf, lettersOf, threadDays, threadsOf, titleOf, type Thread } from "./threads";
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
  // How many threads each day shows, by its key, once "Show more" was pressed on it.
  const [more, setMore] = useState<ReadonlyMap<string, number>>(new Map());

  const open =threads.find((thread) => chosen !== undefined && thread.lines.some((line) => line.call === chosen)) ?? threads[0];
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
          {threadDays(shown).map((day) => {
            const rows = shownOf(day, open, more);
            const left = day.lines.length - rows.length;
            return (
              <Fragment key={day.key}>
                <div className="ib-day">{dayName(day)}</div>
                {rows.map((thread) => (
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
                {left > 0 && (
                  <button
                    type="button"
                    className="ib-more"
                    title={`Show ${Math.min(A_PAGE, left)} more · ${left} left`}
                    aria-label={`Show ${Math.min(A_PAGE, left)} more, ${left} left`}
                    onClick={() => setMore(new Map(more).set(day.key, rows.length + A_PAGE))}
                  >
                    <Icon name="chevron" size={16} />
                  </button>
                )}
              </Fragment>
            );
          })}
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
  const line = thread.latest;
  const live = isLive(line);
  const asking = wantsAPerson(line);
  return (
    <button type="button" className={on ? "ib-row ib-row-on" : "ib-row"} onClick={onOpen}>
      {/* A call up now wears a dot on its avatar: amber while it waits for a person, else green. */}
      <span className={asking ? "ib-avatar ib-avatar-asked" : live ? "ib-avatar ib-avatar-live" : "ib-avatar"}>
        <Avatar name={name} letters={lettersOf(thread)} size={36} round />
      </span>
      <span className="ib-row-main">
        <span className="ib-row-top">
          <span className="ib-row-name">{name}</span>
          {/* The day heads the group, so a row says its hour — or, on the line, how long it has been. */}
          <span className={asking ? "ib-row-time ib-row-time-asked" : live ? "ib-row-time ib-row-time-live" : "ib-row-time"}>
            {live ? elapsed(line.started_at) : line.started_at === null ? "" : clockOf(line.started_at).slice(0, 5)}
          </span>
        </span>
        <span className="ib-row-last">{lastOf(thread)}</span>
        <span className="ib-row-bottom">
          <span className="ib-row-where">{[whose, line.channel].filter((one) => one !== undefined && one !== null).join(" · ")}</span>
          {markOf(line, fresh)}
        </span>
      </span>
    </button>
  );
}

/** The row's mark, when there is one worth it: wants a person, new, or a verdict that broke. A call that held says nothing. */
function markOf(line: Thread["latest"], fresh: boolean): ReactNode | null {
  if (wantsAPerson(line)) {
    return (
      <Pill tone="amber" small>
        wants a person
      </Pill>
    );
  }
  // New, not how many: the door counts calls and lines, which is not what a reader means by messages.
  if (fresh) return <span className="ib-new" aria-label="new" />;
  const score = line.score;
  if (score === null || score === undefined || score.judged === 0 || score.passed) return null;
  return (
    <Pill tone="red" small>
      broke {score.held}/{score.judged}
    </Pill>
  );
}

// A busy day shows this many threads and a button for the next as many: paged, never a scroll
// inside the list's own scroll.
const A_PAGE = 5;

/** The threads a day shows: a page, or as many as "Show more" asked for — always down to the one open, and every one on the line. */
function shownOf(day: CallDay<Thread>, open: Thread | undefined, more: ReadonlyMap<string, number>): Thread[] {
  if (day.name === "live") return day.lines;
  const reaching = open === undefined ? 0 : day.lines.indexOf(open) + 1;
  return day.lines.slice(0, Math.max(more.get(day.key) ?? A_PAGE, reaching));
}

/** A group's title: who is on the line now, then Today, Yesterday and every day before by its date. */
function dayName(day: CallDay<Thread>): string {
  switch (day.name) {
    case "live":
      return "On the line";
    case "unstarted":
      return "Not started";
    case "today":
      return "Today";
    case "yesterday":
      return "Yesterday";
    case "before":
      return dayOf(day.at);
  }
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
