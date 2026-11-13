/** Every call in one table: searched by the gateway, grouped by day, a whole id pasted and Enter opens it. */

import { Fragment, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { byDay, elapsed, isARun, isLive, isSimulated, whoOn } from "@pinecall/core/calls";
import { floorMoved, matches, useServerSearch, type Filter } from "@pinecall/core/calls-search";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { AvatarOf } from "../apps/avatar";
import { lengthOf, utcDay } from "../lib/format";
import { useOrg } from "../lib/org";
import { Select } from "../ui/select";
import { useCallMenu } from "./call-menu";
import { Face } from "./face";
import { AgentPick, StatusChips } from "./filters";
import { copyOf, goldenOf, hourOf, lettersFor, liveFirst, simulationOf, standingOf, webVisitor } from "./format";
import { keeps } from "./status";
import { dayName } from "./threads";
import type { CallsUrl } from "./url";
import { useNow } from "./use-now";

// A call id as the log names one: pasted whole, Enter opens it even when it is not on the page.
const A_CALL = /^call[_-][\w+-]{6,}$/;

const CHANNELS = [
  { value: "", label: "Every channel" },
  { value: "web", label: "Web" },
  { value: "phone", label: "Phone" },
  { value: "whatsapp", label: "WhatsApp" },
];

/** A row opens the call beside its thread; the status picked goes with it. */
function hrefOf(call: string, url: CallsUrl): string {
  return `/calls/${encodeURIComponent(call)}${url.status === "" ? "" : `?status=${url.status}`}`;
}

function Row({ line, to, now, onErased }: { line: SessionLine; to: string; now: number; onErased: (call: string) => void }): ReactNode {
  const menu = useCallMenu(onErased);
  const { whose } = useOrg();
  const who = isARun(line) ? goldenOf(line.call) : isSimulated(line) ? simulationOf(line.call) : whoOn(line, webVisitor);
  const live = isLive(line);
  const standing = standingOf(line);
  const copy = copyOf(line, whose?.subject ?? null);
  return (
    <Link to={to} className="calls-tr dash-row" title={line.call} onContextMenu={(event) => menu(event, line, who)}>
      <Face name={who} letters={isARun(line) ? "G" : isSimulated(line) ? "S" : lettersFor(line.caller?.name, line.direction === "outbound" ? line.to : line.from)} on={live ? (standing.mood === "warn" ? "asking" : "live") : null} />
      <span className="calls-td-who">
        <span className="calls-td-name dash-clip">{who}</span>
        <span className="dash-quiet dash-clip">{line.outcome ?? (live ? (isARun(line) ? "A golden, running now" : "On a call now") : "Nothing was said")}</span>
      </span>
      <span className="calls-td calls-td-agent calls-td-worn">
        <AvatarOf name={line.agent} size={20} />
        <span className="dash-clip">{line.agent}</span>
      </span>
      <span className="calls-td calls-td-channel dash-clip">
        <span className="dash-first">{line.channel ?? "—"}</span>
        {line.direction === "outbound" && ", out"}
        {copy !== undefined && `, ${copy}`}
      </span>
      <span className="calls-td calls-td-ended">
        <span className={`calls-standing dash-mood-${standing.mood}`}>{standing.text}</span>
      </span>
      <span className="calls-td calls-td-judges">
        {line.score != null ? (
          <span className={line.score.passed ? "calls-held" : "calls-tag calls-tag-bad"} title={line.score.reason ?? undefined}>
            {line.score.held}/{line.score.judged}
          </span>
        ) : (
          (line.flags ?? []).includes("escalated") && <span className="calls-tag calls-tag-warn">Escalated</span>
        )}
      </span>
      <span className="calls-td calls-td-length">{live ? elapsed(line.started_at, now) : lengthOf(line.started_at, line.ended_at)}</span>
      <span className="calls-td calls-td-at">{line.started_at === null ? "" : hourOf(line.started_at)}</span>
    </Link>
  );
}

export function CallsTable({ lines, url, onErased }: { /** What the page follows, through the agent picked. */ lines: readonly SessionLine[]; url: CallsUrl; onErased: (call: string) => void }): ReactNode {
  const navigate = useNavigate();
  const [pages, setPages] = useState(1);
  const filter: Filter = { query: url.query, agent: url.agent, channel: url.channel };
  // Asked again whenever the followed list moves: a call that rang shows up in the searched page too.
  const searched = useServerSearch("", filter, pages, floorMoved(lines)).found;
  const found = searched !== null ? searched.rows : lines.filter((line) => matches(line, filter.query) && (filter.channel === "" || line.channel === filter.channel));
  const ordered = liveFirst(found.filter((line) => keeps(url.status, line)));
  const now = useNow(ordered.some(isLive));
  const typed = url.query.trim();
  const filtering = url.query !== "" || url.agent !== "" || url.channel !== "" || url.status !== "";

  const open = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Enter" && A_CALL.test(typed)) void navigate(`/calls/${encodeURIComponent(typed)}`);
  };

  return (
    <div className="calls-table">
      <div className="calls-filters">
        <input className="app-input calls-search" aria-label="Search a call id, number or outcome" placeholder="Search a call id, number or outcome" value={url.query} onChange={(event) => url.ask("q", event.target.value)} onKeyDown={open} />
        <StatusChips lines={lines} url={url} />
        <span className="calls-grow" />
        <AgentPick url={url} />
        <div className="calls-pick">
          <Select label="Filter by channel" value={url.channel} items={CHANNELS} onChange={(value) => url.ask("channel", value)} />
        </div>
      </div>
      <section className="dash-card" aria-label="Calls">
        {ordered.length === 0 ? (
          <p className="dash-quiet">{!filtering ? "No call yet. The first one shows up here the moment it starts." : A_CALL.test(typed) ? `It is not on this page. Press Enter to open ${typed} by its id.` : "No call here matches."}</p>
        ) : (
          <div className="dash-rows">
            <div className="calls-tr calls-tr-head dash-row-head" aria-hidden="true">
              <span className="calls-td-face" />
              <span className="calls-td-who">Who</span>
              <span className="calls-td calls-td-agent">Agent</span>
              <span className="calls-td calls-td-channel">Channel</span>
              <span className="calls-td calls-td-ended">Ended</span>
              <span className="calls-td calls-td-judges">Judges</span>
              <span className="calls-td calls-td-length">Length</span>
              <span className="calls-td calls-td-at">At</span>
            </div>
            {byDay(ordered, utcDay).map((day) => (
              <Fragment key={day.key}>
                <div className="calls-day calls-day-table">
                  <span>{dayName(day)}</span>
                  <span>
                    {day.lines.length} {day.lines.length === 1 ? "call" : "calls"}
                  </span>
                </div>
                {day.lines.map((line) => (
                  <Row key={line.call} line={line} to={hrefOf(line.call, url)} now={now} onErased={onErased} />
                ))}
              </Fragment>
            ))}
          </div>
        )}
        {searched !== null && searched.total > searched.rows.length && (
          <div className="calls-table-foot">
            <span className="dash-quiet">
              {searched.rows.length} of {searched.total}
            </span>
            <button type="button" className="app-button" onClick={() => setPages(pages + 1)}>
              Load more
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
