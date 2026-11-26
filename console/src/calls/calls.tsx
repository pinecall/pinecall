/** Calls: every conversation of the org, as threads beside the one open or as one table; the address says which, through which status, and which call. */

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Navigate, useNavigate, useParams } from "react-router";

import { floorMoved, useServerSearch } from "@pinecall/core/calls-search";
import { type SessionLine } from "@pinecall/core/wire/rest";
import { Icon } from "../shell/icons";
import { useOrg } from "../lib/org";
import { usePhone } from "../lib/phone";
import { PageHead } from "../shell/page-head";
import { ThreadList } from "./list";
import { OpenCall } from "./open-call";
import { keeps } from "./status";
import { CallsTable } from "./table";
import { threadsOf, titleOf, type Thread } from "./threads";
import { isATest, thingOf, typeOf } from "./kind";
import { askedOf, useCallsUrl } from "./url";
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
  // A phone opens on the list, a tap away from each one; a desk opens the first beside it.
  const phone = usePhone();
  const { call: chosen } = useParams();
  const url = useCallsUrl();
  const { lines: read } = useOrg();
  const navigate = useNavigate();
  // The feed says nothing of an erasure, so the list would keep the call until its next read: taken out here.
  const [erased, setErased] = useState<ReadonlySet<string>>(new Set());
  const lines = useMemo(() => (erased.size === 0 ? read : read.filter((line) => !erased.has(line.call))), [read, erased]);
  const [details, setDetails] = useState(() => window.innerWidth > DETAILS_OPEN_FROM);
  const { agent, status } = url;
  // One page lists every conversation, whatever it came by, narrowed to the kind picked. Simulated callers and
  // golden runs are tests, not people: they are listed only when asked for.
  const { type, tests } = url;
  const [pages, setPages] = useState(1);
  // The kind, the tests and the words are asked of the gateway: the page holds the org's fifty newest conversations,
  // and what is picked may be none of them. What the page follows live is laid over the answer, so a row is as fresh.
  const searched = useServerSearch("", askedOf(url, url.query), pages, floorMoved(lines), !url.table).found;
  const mine = useMemo(() => {
    const wanted = (line: SessionLine): boolean => (agent === "" || line.agent === agent) && (type === "" || typeOf(line) === type) && (tests || !isATest(line));
    const followed = lines.filter(wanted);
    if (searched === null) return followed;
    const fresh = new Map(followed.map((line) => [line.call, line]));
    const found = searched.rows.filter((line) => !erased.has(line.call) && wanted(line)).map((line) => fresh.get(line.call) ?? line);
    const known = new Set(found.map((line) => line.call));
    // A call that began since the gateway was asked is followed already: listed too, unless words narrow the list.
    const begun = url.query.trim() === "" ? followed.filter((line) => !known.has(line.call)) : [];
    return [...begun, ...found].sort((one, other) => (other.started_at ?? Infinity) - (one.started_at ?? Infinity));
  }, [lines, searched, erased, agent, type, tests, url.query]);
  // The same function while there is more, so the end of the list is watched once and asks once a page.
  const more = searched !== null && searched.next !== null;
  const readOn = useCallback(() => setPages((was) => was + 1), []);
  const older = more ? readOn : undefined;
  // One row a person, their calls under it: a visitor, a number, a WhatsApp contact (Bernardo, 2026-11-25).
  const threads = useMemo(() => threadsOf(mine.filter((line) => keeps(status, line))), [mine, status]);
  // Who the person is does not depend on the status picked: their other conversations are all of them.
  const everyone = useMemo(() => threadsOf(lines), [lines]);
  const first = threads[0];
  const onErased = (call: string): void => {
    setErased((was) => new Set(was).add(call));
    if (call === chosen) void navigate(`${url.base}${url.search}`, { replace: true });
  };

  const views = (
    <div className="dash-switch calls-listed" role="group" aria-label="How the calls are listed">
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
  const opened = chosen === undefined ? undefined : lines.find((line) => line.call === chosen);
  if (!phone && chosen === undefined && first !== undefined) return <Navigate to={`${url.base}/${encodeURIComponent(first.latest.call)}${url.search}`} replace />;

  const person = holding(everyone, chosen);
  return (
    <>
      <PageHead open={chosen === undefined ? undefined : person === undefined ? (opened === undefined ? "A call" : thingOf(opened) === "email thread" ? "An email" : `A ${thingOf(opened)}`) : titleOf(person)} back={`${url.base}${url.search}`}>
        {views}
        {chosen !== undefined && (
          <button type="button" className={details ? "app-button calls-toggle calls-toggle-on" : "app-button calls-toggle"} aria-pressed={details} onClick={() => setDetails(!details)}>
            <Icon name="quality" size={14} />
            Details
          </button>
        )}
      </PageHead>
      <div className="app-layout calls-layout">
        <ThreadList threads={threads} lines={mine} open={holding(threads, chosen)} shown={chosen} url={url} onErased={onErased} searched={searched !== null} onOlder={older} />
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
