/** The column of conversations: one thread per person under its day, the search and the filters over them, and j and k to move through them. */

import { Fragment, useEffect, useRef, type ReactNode, type Ref } from "react";
import { Link, useNavigate } from "react-router";

import { elapsed, isLive, wantsAPerson } from "@pinecall/core/calls";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { useCallMenu } from "./call-menu";
import { ReadsOn } from "./older";
import { browserOf, countryName, flagOf } from "./visitor";
import { countryOfNumber } from "./countries";
import { useOrg } from "../lib/org";
import { Face } from "./face";
import { AgentPick, StatusChips, TypePick } from "./filters";
import { lengthOf } from "../lib/format";
import { copyOf, dayOf, hourOf } from "./format";
import { useSubject } from "./subject";
import { dayName, isOnTheLine, lastOf, lettersOf, threadDays, titleOf, type Thread } from "./threads";
import { kindSaid, thingOf } from "./kind";
import { CALLS, TYPES, type CallsUrl } from "./url";
import { useNow } from "./use-now";

// A busy day shows this many threads and a button for the next as many.

/** The threads a day shows: a page, or as many as "Show more" asked for; always down to the one open, and every one on the line. */

// Typing is typing: only with the focus outside every field do the letters move the list.
function inAField(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && target.closest("input, textarea, select, [contenteditable='true'], .ui-select-menu") !== null;
}

/** What the judges made of it, or that somebody has to answer. A call nobody judged says nothing. */
function Mark({ line }: { line: SessionLine }): ReactNode {
  if (wantsAPerson(line)) return <span className="calls-tag calls-tag-warn">Wants a person</span>;
  const score = line.score;
  if (score === null || score === undefined || score.judged === 0) return null;
  if (score.passed) {
    return (
      <span className="calls-held" title="Every judge held">
        {score.held}/{score.judged}
      </span>
    );
  }
  return (
    <span className="calls-tag calls-tag-bad" title={score.reason ?? undefined}>
      Broke {score.held}/{score.judged}
    </span>
  );
}

function ThreadRow({ thread, to, on, now, held, onErased }: { thread: Thread; to: string; on: boolean; now: number; held: Ref<HTMLAnchorElement> | undefined; onErased: (call: string) => void }): ReactNode {
  const menu = useCallMenu(onErased);
  const { whose } = useOrg();
  const line = thread.latest;
  // A written conversation is open, not on the line: it has no clock running and no dot.
  const live = isOnTheLine(line);
  const asking = wantsAPerson(line);
  const name = titleOf(thread);
  // An email thread is listed by its subject, as a mailbox lists it; any other by how it went.
  const subject = useSubject(line.call, line.channel === "email");
  const where = [line.agent, kindSaid(line), browserOf(line.visitor?.user_agent), copyOf(line, whose?.subject ?? null)].filter((one) => one !== undefined && one !== null).join(" · ");
  // A web visitor's country is where the gateway saw them; a number's, its calling code's.
  const country = line.visitor?.country ?? countryOfNumber(thread.contact);
  const flag = flagOf(country);
  return (
    <Link ref={held} to={to} className={on ? "app-row app-row-on calls-row" : "app-row calls-row"} aria-current={on ? "true" : undefined} onContextMenu={(event) => menu(event, line, name)}>
      <Face name={name} letters={lettersOf(thread)} on={asking ? "asking" : live ? "live" : null} />
      <span className="calls-row-main">
        <span className="calls-row-top">
          <span className="dash-clip">
            {flag !== null && (
              <span className="calls-flag" title={countryName(country) ?? undefined} aria-label={countryName(country) ?? undefined}>
                {flag}
              </span>
            )}
            {name}
          </span>
          {/* The day heads the group, so a row says its hour, or on the line how long it has been. */}
          <span className={asking ? "calls-row-time dash-mood-warn" : live ? "calls-row-time dash-mood-good" : "calls-row-time"}>{live ? elapsed(line.started_at, now) : line.started_at === null ? "" : hourOf(line.started_at)}</span>
        </span>
        <span className="app-row-under dash-clip">{subject ?? lastOf(thread)}</span>
        <span className="calls-row-foot">
          <span className="calls-row-where dash-clip">{where}</span>
          {thread.lines.length > 1 && <span className="calls-count">{thread.lines.length} {thread.lines.every((one) => thingOf(one) === "call") ? "calls" : "conversations"}</span>}
          <Mark line={line} />
        </span>
      </span>
    </Link>
  );
}

// A row is a person and shows their newest call: every call of theirs is listed under it once it is
// open. Until 0.11.39 the earlier ones were only in the details panel, and a person who called three
// times read as one call.
/** Every call of the open thread, newest first, the one shown marked. */
function ThreadCalls({ thread, shown, search, now, onErased }: { thread: Thread; shown: string | undefined; search: string; now: number; onErased: (call: string) => void }): ReactNode {
  const menu = useCallMenu(onErased);
  if (thread.lines.length < 2) return null;
  return (
    <div className="calls-theirs" aria-label="Their calls">
      {thread.lines.map((line) => (
        <Link key={line.call} to={`${CALLS}/${encodeURIComponent(line.call)}${search}`} className={line.call === shown ? "calls-their calls-their-on" : "calls-their"} aria-current={line.call === shown ? "true" : undefined} onContextMenu={(event) => menu(event, line, titleOf(thread))}>
          <span className="calls-their-when">{line.started_at === null ? "—" : `${dayOf(line.started_at)}, ${hourOf(line.started_at)}`}</span>
          <span className={isOnTheLine(line) ? "calls-their-how dash-mood-good" : "calls-their-how"}>{isOnTheLine(line) ? elapsed(line.started_at, now) : isLive(line) ? "open" : lengthOf(line.started_at, line.ended_at)}</span>
          <Mark line={line} />
        </Link>
      ))}
    </div>
  );
}

// What an empty list says: of the kind picked when one is, and where the tests went when they are hidden.
function nothingYet(url: CallsUrl): string {
  const hidden = url.tests ? "" : " Simulated callers and golden runs are tests and are hidden: turn Tests on to list them.";
  if (url.query.trim() !== "") return `Nothing matches “${url.query.trim()}”.${hidden}`;
  if (url.type === "email") return `No email yet. Connect a mailbox on Mailboxes, or in an agent's Channels tab, and every email written to it shows up here.${hidden}`;
  if (url.type !== "") return `Nothing in ${TYPES.find((one) => one.value === url.type)?.label ?? "this kind"}.${hidden || " Pick another kind above, or everything."}`;
  return `Nothing yet. The first call, chat, message or email shows up here the moment it starts.${hidden}`;
}

export function ThreadList({ threads, lines, open, shown: shownCall, url, onErased, searched, onOlder }: { threads: readonly Thread[]; /** The calls in view, before the status: what the chips count. */ lines: readonly SessionLine[]; open: Thread | undefined; /** The call on screen, one of the open thread's. */ shown: string | undefined; /** A call erased from a row's menu: out of the list. */ onErased: (call: string) => void; url: CallsUrl; /** The gateway searched the words: the rows are its answer, and are not narrowed again here. */ searched: boolean; /** Asks the gateway for the page before these, as the end of the list comes into view; none when these are all. */ onOlder: (() => void) | undefined }): ReactNode {
  const navigate = useNavigate();
  const now = useNow(threads.some((thread) => isOnTheLine(thread.latest)));
  const openRow = useRef<HTMLAnchorElement>(null);
  const words = url.query.trim().toLowerCase();
  const shown = searched ? threads : threads.filter((thread) => words === "" || `${titleOf(thread)} ${thread.handle} ${lastOf(thread)}`.toLowerCase().includes(words));
  const days = threadDays(shown).map((day) => ({ day, rows: day.lines }));
  const order = days.flatMap(({ rows }) => rows);
  const hrefOf = (thread: Thread): string => `${url.base}/${encodeURIComponent(thread.latest.call)}${url.search}`;

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if ((event.key !== "j" && event.key !== "k") || event.metaKey || event.ctrlKey || event.altKey || event.defaultPrevented || inAField(event.target)) return;
      const at = open === undefined ? -1 : order.indexOf(open);
      const next = order[event.key === "j" ? at + 1 : at - 1];
      if (next !== undefined) void navigate(hrefOf(next), { replace: true });
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  const contact = open?.key;
  useEffect(() => {
    if (contact !== undefined) openRow.current?.scrollIntoView({ block: "nearest" });
  }, [contact]);

  return (
    <aside className="app-list" aria-label="Calls">
      <div className="app-list-head">
        <span className="app-list-title">Calls</span>
        <span className="dash-quiet">{threads.length}</span>
      </div>
      <input className="app-input" aria-label="Search a name, a number or an address" placeholder="Search a name, a number or an address" value={url.query} onChange={(event) => url.ask("q", event.target.value)} />
      <AgentPick url={url} />
      <TypePick url={url} />
      <div className="calls-filters">
        <StatusChips lines={lines} url={url} />
      </div>
      <div className="app-rows">
        {threads.length === 0 && <p className="dash-quiet app-none">{lines.length === 0 ? nothingYet(url) : "Nothing here right now."}</p>}
        {threads.length > 0 && shown.length === 0 && <p className="dash-quiet app-none">Nobody here matches “{url.query}”.</p>}
        {days.map(({ day, rows }) => (
          <Fragment key={day.key}>
            <div className="calls-day">{dayName(day)}</div>
            {rows.map((thread) => (
              <Fragment key={thread.key}>
                <ThreadRow thread={thread} to={hrefOf(thread)} on={thread === open} now={now} held={thread === open ? openRow : undefined} onErased={onErased} />
                {thread === open && <ThreadCalls thread={thread} shown={shownCall} search={url.search} now={now} onErased={onErased} />}
              </Fragment>
            ))}
          </Fragment>
        ))}
        <ReadsOn onOlder={onOlder} />
      </div>
    </aside>
  );
}
