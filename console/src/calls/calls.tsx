/** Calls: every conversation of the org, as threads beside the one open or as one table; the address says which, through which status, and which call. */

import { useMemo, useState, type ReactNode } from "react";
import { Navigate, useNavigate, useParams } from "react-router";

import { Icon } from "../shell/icons";
import { useOrg } from "../lib/org";
import { PageHead } from "../shell/page-head";
import { useGrouped } from "./grouped";
import { ThreadList } from "./list";
import { OpenCall } from "./open-call";
import { keeps } from "./status";
import { CallsTable } from "./table";
import { threadsOf, titleOf, type Thread } from "./threads";
import { useCallsUrl } from "./url";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "./calls.css";
import "./conversation.css";
import "./details.css";

// Below this the page cannot hold the list, the call and the details at once, and the list would be what goes: the details wait to be asked for.
const DETAILS_OPEN_FROM = 1500;

function holding(threads: readonly Thread[], call: string | undefined): Thread | undefined {
  return call === undefined ? undefined : threads.find((thread) => thread.lines.some((line) => line.call === call));
}

export function CallsPage(): ReactNode {
  const { call: chosen } = useParams();
  const url = useCallsUrl();
  const { lines: read } = useOrg();
  const navigate = useNavigate();
  const [grouped, flipGrouped] = useGrouped();
  // The feed says nothing of an erasure, so the list would keep the call until its next read: taken out here.
  const [erased, setErased] = useState<ReadonlySet<string>>(new Set());
  const lines = useMemo(() => (erased.size === 0 ? read : read.filter((line) => !erased.has(line.call))), [read, erased]);
  const [details, setDetails] = useState(() => window.innerWidth > DETAILS_OPEN_FROM);
  const { agent, status } = url;
  const mine = useMemo(() => (agent === "" ? lines : lines.filter((line) => line.agent === agent)), [lines, agent]);
  const threads = useMemo(() => threadsOf(mine.filter((line) => keeps(status, line)), grouped), [mine, status, grouped]);
  // Who the person is does not depend on the status picked: their other conversations are all of them.
  const everyone = useMemo(() => threadsOf(lines), [lines]);
  const first = threads[0];
  const onErased = (call: string): void => {
    setErased((was) => new Set(was).add(call));
    if (call === chosen) void navigate(`/calls${url.search}`, { replace: true });
  };

  const views = (
    <div className="dash-switch" role="group" aria-label="How the calls are listed">
      <button type="button" className={url.table ? "" : "dash-switch-on"} aria-pressed={!url.table} onClick={() => url.ask("view", "")}>
        Threads
      </button>
      <button type="button" className={url.table ? "dash-switch-on" : ""} aria-pressed={url.table} onClick={() => url.ask("view", "table")}>
        Table
      </button>
    </div>
  );

  if (url.table) {
    return (
      <>
        <PageHead>{views}</PageHead>
        <CallsTable lines={mine} url={url} onErased={onErased} />
      </>
    );
  }

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  if (chosen === undefined && first !== undefined) return <Navigate to={`/calls/${encodeURIComponent(first.latest.call)}${url.search}`} replace />;

  const person = holding(everyone, chosen);
  return (
    <>
      <PageHead open={chosen === undefined ? undefined : person === undefined ? "A call" : titleOf(person)}>
        {views}
        {chosen !== undefined && (
          <button type="button" className={details ? "app-button calls-toggle calls-toggle-on" : "app-button calls-toggle"} aria-pressed={details} onClick={() => setDetails(!details)}>
            <Icon name="quality" size={14} />
            Details
          </button>
        )}
      </PageHead>
      <div className="app-layout calls-layout">
        <ThreadList threads={threads} lines={mine} open={holding(threads, chosen)} shown={chosen} url={url} grouped={grouped} onGroup={flipGrouped} onErased={onErased} />
        <div className="app-open">
          {chosen === undefined ? (
            <p className="dash-quiet app-open-note">Pick a conversation to read it here.</p>
          ) : (
            <OpenCall key={chosen} call={chosen} person={person} search={url.search} details={details} onDetails={setDetails} />
          )}
        </div>
      </div>
    </>
  );
}
