/** Calls as a table: what the URL searches and filters by, grouped by day, the calls up right now on top. */

import { type SessionLine } from "@pinecall/core/wire/rest";
import { Fragment, useState, type KeyboardEvent, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { byDay, isLive, whoOn, type CallDay } from "@pinecall/core/calls";
import { floorMoved, matches, useServerSearch, type Filter } from "@pinecall/core/calls-search";
import { clockOf, dayOf, duration, lettersFor, liveFirst, utcDay, webVisitor } from "../../lib/format";
import { Avatar, Button, Card, CardFoot, Empty, Input, Pill, Refused, Select, SelectItem, TableHead, TableRow, type Tone } from "../../ui";
import { keeps, type Status } from "./status";

// A call id as the log names one: pasted whole, Enter opens it even when it is not on the page.
const A_CALL = /^call[_-][\w+-]{6,}$/;

// A row leads with WHO was on the call — a person, not an id — then what was last said under
// them, the way a thread reads. The id is the row's title, and the row opens the call beside its thread.
const ORG_COLUMNS = "28px minmax(0,2fr) minmax(90px,0.7fr) 84px 132px 70px 60px 52px";
const AGENT_COLUMNS = "28px minmax(0,2fr) 84px 132px 70px 60px 52px";
const ORG_LABELS = ["", "Who", "Agent", "Channel", "Ended", "Judges", "Length>", "At>"];
const AGENT_LABELS = ["", "Who", "Channel", "Ended", "Judges", "Length>", "At>"];
const CHANNELS = ["web", "phone", "whatsapp"] as const;

// The filters are the URL's and nothing else's: `?q=`, `?agent=` and `?channel=` are links people
// paste, and so is the status Calls' chips pick (`?status=`), which reaches the table already applied.

/**
 * The list. `lines` is what the screen already follows — the org's, or the agent in view's,
 * through the status picked — and it is searched here; a gateway whose sessions door searches by
 * itself (it answers a `total`) is asked instead, the status applied to what it answers, and its
 * total is said.
 */
export function ConversationList({
  lines,
  error,
  agent,
  agents,
  status,
}: {
  lines: SessionLine[];
  error: string | null;
  /** The agent in view, or "" for every agent. */
  agent: string;
  /** The slugs the agent filter offers, with every agent in view. */
  agents: string[];
  status: Status;
}): ReactNode {
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [pages, setPages] = useState(1);
  const org = agent === "";
  // An agent fixed by the path is not one to choose: `?agent=` is the org's list alone.
  const filter: Filter = { query: search.get("q") ?? "", agent: org ? (search.get("agent") ?? "") : "", channel: search.get("channel") ?? "" };
  // Asked again whenever the followed list moves: a call that rang shows up in the searched page too.
  const searched = useServerSearch(agent, filter, pages, floorMoved(lines)).found;

  const asked = (name: string, value: string): void => {
    const next = new URLSearchParams(search);
    if (value === "") next.delete(name);
    else next.set(name, value);
    setSearch(next, { replace: true });
  };

  const found =
    searched !== null
      ? searched.rows
      : lines.filter(
          (line) => matches(line, filter.query) && (filter.agent === "" || line.agent === filter.agent) && (filter.channel === "" || line.channel === filter.channel),
        );
  const shown = found.filter((line) => keeps(status, line));
  const ordered = liveFirst(shown);

  const open = (event: KeyboardEvent<HTMLInputElement>): void => {
    const typed = filter.query.trim();
    if (event.key === "Enter" && A_CALL.test(typed)) void navigate(`${base}/${typed}`);
  };

  const columns = org ? ORG_COLUMNS : AGENT_COLUMNS;
  // A row opens the call in Threads, the agent in view kept in view.
  const base = org ? "/calls" : `/a/${encodeURIComponent(agent)}/calls`;
  const filtering = filter.query !== "" || filter.agent !== "" || filter.channel !== "" || status !== "";

  return (
    <>
      <div className="calls-filters">
        <Input
          size="sm"
          className="calls-search"
          placeholder="Search a call id, number or outcome"
          aria-label="Search a call id, number or outcome"
          value={filter.query}
          onChange={(event) => asked("q", event.target.value)}
          onKeyDown={open}
        />
        {org && (
          <Select size="sm" className="calls-select" aria-label="Filter by agent" value={filter.agent} onValueChange={(value) => asked("agent", value)}>
            <SelectItem value="">Every agent</SelectItem>
            {agents.map((slug) => (
              <SelectItem key={slug} value={slug}>
                {slug}
              </SelectItem>
            ))}
          </Select>
        )}
        <Select size="sm" className="calls-select" aria-label="Filter by channel" value={filter.channel} onValueChange={(value) => asked("channel", value)}>
          <SelectItem value="">Every channel</SelectItem>
          {CHANNELS.map((channel) => (
            <SelectItem key={channel} value={channel}>
              {channel}
            </SelectItem>
          ))}
        </Select>
      </div>

      <Refused>{error}</Refused>

      <Card>
        {ordered.length === 0 ? (
          <Empty>
            {filtering ? (
              A_CALL.test(filter.query.trim()) ? (
                <>Not on this page — press Enter to open {filter.query.trim()} by its id.</>
              ) : (
                <>No call here matches. The search reads the calls this page has listed.</>
              )
            ) : (
              <>
                No call yet. The log is written during the call, so one appears here the moment it starts — from the browser, from{" "}
                <span className="ui-fixed">pinecall chat</span>, or from the telephone.
              </>
            )}
          </Empty>
        ) : (
          <>
            <TableHead columns={columns} labels={org ? ORG_LABELS : AGENT_LABELS} />
            {byDay(ordered, utcDay).map((group) => (
              <Fragment key={group.key}>
                <div className="calls-day">
                  <span className="calls-day-name">{dayName(group)}</span>
                  <span className="calls-day-count">
                    {group.lines.length} {group.lines.length === 1 ? "call" : "calls"}
                  </span>
                </div>
                {group.lines.map((line) => (
                  <Row key={line.call} line={line} columns={columns} org={org} base={base} />
                ))}
              </Fragment>
            ))}
          </>
        )}
        {searched !== null && searched.total > searched.rows.length && (
          <CardFoot>
            <span>
              {searched.rows.length} of {searched.total}
            </span>
            <span className="calls-more">
              <Button size="sm" onClick={() => setPages(pages + 1)}>
                Load more
              </Button>
            </span>
          </CardFoot>
        )}
      </Card>
    </>
  );
}

/** One call: who, what was last said, which agent and door, how it ended, what the judges made of it, how long, when. */
function Row({ line, columns, org, base }: { line: SessionLine; columns: string; org: boolean; base: string }): ReactNode {
  const who = whoOn(line, webVisitor);
  const live = isLive(line);
  const ended = endedAs(line);
  return (
    <TableRow columns={columns} to={`${base}/${line.call}`}>
      <span className={live ? "calls-who-avatar calls-who-avatar-live" : "calls-who-avatar"} title={line.call}>
        <Avatar name={who} letters={lettersFor(line.caller?.name, line.direction === "outbound" ? line.to : line.from)} size={28} round />
      </span>
      <span className="calls-who">
        <span className="calls-who-name ui-clip">{who}</span>
        <span className="calls-who-said ui-clip">{line.outcome ?? (live ? "on the line now" : "nothing was said")}</span>
      </span>
      {org && <span className="ui-cell-ink ui-clip">{line.agent}</span>}
      <span className="ui-cell">
        {line.channel ?? "—"}
        {line.direction === "outbound" && <span className="calls-out"> · out</span>}
      </span>
      <span>
        <Pill tone={ended.tone} small>
          {ended.text}
        </Pill>
      </span>
      <span>
        {line.score != null && (
          <Pill tone={line.score.passed ? "green" : "red"} small>
            {line.score.held}/{line.score.judged}
          </Pill>
        )}
        {line.score == null && (line.flags ?? []).includes("escalated") && (
          <Pill tone="amber" small>
            escalated
          </Pill>
        )}
      </span>
      <span className="ui-cell ui-cell-right calls-num">{live ? "" : duration(line)}</span>
      <span className="ui-cell ui-cell-right calls-num">{clockOf(line.started_at).slice(0, 5)}</span>
    </TableRow>
  );
}

// How a call ended, in the operator's words and tint: the caller's own hang-up is the quiet one,
// a hand-off is worth a glance, and anything the platform did is red.
const ENDINGS: Record<string, { text: string; tone: Tone }> = {
  caller_hung_up: { text: "caller hung up", tone: "gray" },
  agent_hung_up: { text: "agent hung up", tone: "gray" },
  supervisor_ended: { text: "supervisor ended", tone: "indigo" },
  transferred: { text: "transferred", tone: "amber" },
  no_answer: { text: "no answer", tone: "muted" },
  busy: { text: "busy", tone: "muted" },
  dial_failed: { text: "dial failed", tone: "red" },
  timeout: { text: "timed out", tone: "red" },
  drained: { text: "drained", tone: "red" },
  app_detached: { text: "app detached", tone: "red" },
  error: { text: "error", tone: "red" },
};

/** How the call stands, as a pill: live and its state, or the reason it ended. */
function endedAs(line: SessionLine): { text: string; tone: Tone } {
  // A caller waiting for somebody to take the line is the one row a person reading this list has
  // to act on, so it says so instead of saying "live" like every other call up right now.
  if (isLive(line) && line.attention?.status === "open") return { text: "● wants a person", tone: "amber" };
  if (isLive(line)) return { text: line.status === "active" ? "● live" : line.status, tone: "green" };
  if (line.end_reason === null) return { text: "ended", tone: "gray" };
  return ENDINGS[line.end_reason] ?? { text: line.end_reason.replace(/_/g, " "), tone: "gray" };
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/**
 * A day's title over its calls (core's `byDay` cuts them, by UTC day, as every time on this page
 * is): the live calls under "On a call now", then Today, Yesterday and every day before by its
 * date. A call that has not started has no day, and closes the list.
 */
function dayName(day: CallDay<SessionLine>): string {
  switch (day.name) {
    case "live":
      return "On a call now";
    case "unstarted":
      return "Not started";
    case "today":
      return "Today";
    case "yesterday":
      return "Yesterday";
    case "before":
      return `${WEEKDAYS[new Date(day.at * 1000).getUTCDay()]} ${dayOf(day.at)}`;
  }
}
