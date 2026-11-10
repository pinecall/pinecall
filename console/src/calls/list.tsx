/** The column of conversations: one thread per person under its day, the search and the filters over them, and j and k to move through them. */

import { Fragment, useEffect, useRef, useState, type ReactNode, type Ref } from "react";
import { Link, useNavigate } from "react-router";

import { elapsed, isLive, wantsAPerson, type CallDay } from "@pinecall/core/calls";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { useOrg } from "../lib/org";
import { Face } from "./face";
import { AgentPick, StatusChips } from "./filters";
import { copyOf, hourOf } from "./format";
import { dayName, lastOf, lettersOf, threadDays, titleOf, type Thread } from "./threads";
import type { CallsUrl } from "./url";
import { useNow } from "./use-now";

// A busy day shows this many threads and a button for the next as many.
const A_PAGE = 5;

/** The threads a day shows: a page, or as many as "Show more" asked for; always down to the one open, and every one on the line. */
function shownOf(day: CallDay<Thread>, open: Thread | undefined, more: ReadonlyMap<string, number>): Thread[] {
  if (day.name === "live") return day.lines;
  const reaching = open === undefined ? 0 : day.lines.indexOf(open) + 1;
  return day.lines.slice(0, Math.max(more.get(day.key) ?? A_PAGE, reaching));
}

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

function ThreadRow({ thread, to, on, now, held }: { thread: Thread; to: string; on: boolean; now: number; held: Ref<HTMLAnchorElement> | undefined }): ReactNode {
  const { whose } = useOrg();
  const line = thread.latest;
  const live = isLive(line);
  const asking = wantsAPerson(line);
  const name = titleOf(thread);
  const where = [line.agent, line.channel, copyOf(line, whose?.subject ?? null)].filter((one) => one !== undefined && one !== null).join(" · ");
  return (
    <Link ref={held} to={to} className={on ? "app-row app-row-on calls-row" : "app-row calls-row"} aria-current={on ? "true" : undefined}>
      <Face name={name} letters={lettersOf(thread)} on={asking ? "asking" : live ? "live" : null} />
      <span className="calls-row-main">
        <span className="calls-row-top">
          <span className="dash-clip">{name}</span>
          {/* The day heads the group, so a row says its hour, or on the line how long it has been. */}
          <span className={asking ? "calls-row-time dash-mood-warn" : live ? "calls-row-time dash-mood-good" : "calls-row-time"}>{live ? elapsed(line.started_at, now) : line.started_at === null ? "" : hourOf(line.started_at)}</span>
        </span>
        <span className="app-row-under dash-clip">{lastOf(thread)}</span>
        <span className="calls-row-foot">
          <span className="calls-row-where dash-clip">{where}</span>
          <Mark line={line} />
        </span>
      </span>
    </Link>
  );
}

export function ThreadList({ threads, lines, open, url }: { threads: readonly Thread[]; /** The calls in view, before the status: what the chips count. */ lines: readonly SessionLine[]; open: Thread | undefined; url: CallsUrl }): ReactNode {
  const navigate = useNavigate();
  const [more, setMore] = useState<ReadonlyMap<string, number>>(new Map());
  const now = useNow(threads.some((thread) => isLive(thread.latest)));
  const openRow = useRef<HTMLAnchorElement>(null);
  const words = url.query.trim().toLowerCase();
  const shown = threads.filter((thread) => words === "" || `${titleOf(thread)} ${thread.handle} ${lastOf(thread)}`.toLowerCase().includes(words));
  const days = threadDays(shown).map((day) => ({ day, rows: shownOf(day, open, more) }));
  const order = days.flatMap(({ rows }) => rows);
  const hrefOf = (thread: Thread): string => `/calls/${encodeURIComponent(thread.latest.call)}${url.search}`;

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

  const contact = open?.contact;
  useEffect(() => {
    if (contact !== undefined) openRow.current?.scrollIntoView({ block: "nearest" });
  }, [contact]);

  return (
    <aside className="app-list" aria-label="Calls">
      <div className="app-list-head">
        <span className="app-list-title">Calls</span>
        <span className="dash-quiet">{threads.length}</span>
      </div>
      <input className="app-input" aria-label="Search a caller or number" placeholder="Search a caller or number" value={url.query} onChange={(event) => url.ask("q", event.target.value)} />
      <AgentPick url={url} />
      <StatusChips lines={lines} url={url} />
      <div className="app-rows">
        {threads.length === 0 && <p className="dash-quiet app-none">{lines.length === 0 ? "No call yet. The first one shows up here the moment it starts." : "No call here right now."}</p>}
        {threads.length > 0 && shown.length === 0 && <p className="dash-quiet app-none">Nobody here matches “{url.query}”.</p>}
        {days.map(({ day, rows }) => {
          const left = day.lines.length - rows.length;
          return (
            <Fragment key={day.key}>
              <div className="calls-day">{dayName(day)}</div>
              {rows.map((thread) => (
                <ThreadRow key={thread.contact} thread={thread} to={hrefOf(thread)} on={thread === open} now={now} held={thread === open ? openRow : undefined} />
              ))}
              {left > 0 && (
                <button type="button" className="calls-more" onClick={() => setMore(new Map(more).set(day.key, rows.length + A_PAGE))}>
                  Show {Math.min(A_PAGE, left)} more of {left}
                </button>
              )}
            </Fragment>
          );
        })}
      </div>
    </aside>
  );
}
