/** Cases, the same page as Agents and Simulations: the causes a judge's breaks share and what a person kept in a list, beside the one open with the move that fixes it. */

import { Fragment, useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { dayName } from "../calls/threads";
import { PageHead } from "../shell/page-head";
import { decideCase } from "../test/door";
import { GoldenFormPanel } from "../test/golden-panel";
import { saidIn } from "../test/fold";
import { AgentPick } from "../ui/agent-pick";
import { CaseOpen, CasePanel } from "./case-panel";
import { daysOf } from "./days";
import { decideGroup, readCases, readGroups, type CaseGroup, type EvalCase, type Listed } from "./door";
import { fromOf, Group } from "./group";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
import "../quality/quality.css";
import "../test/test.css";
import "./cases.css";

const HOME = "/cases";
const AGENT = "agent";
const SHOW = "show";
const GROUP = "group";
const CASE = "case";

type Show = CaseGroup["status"];

const SHOWS: readonly { show: Show; name: string }[] = [
  { show: "pending", name: "Waiting" },
  { show: "approved", name: "Goldens" },
  { show: "dismissed", name: "Dismissed" },
];

const NOTHING: Record<Show, string> = {
  pending: "Nothing waits for you. A call a judge breaks on lands here, grouped with the others that broke the same way.",
  approved: "No case is a golden yet. Approve one and every run plays it again.",
  dismissed: "Nothing was dismissed.",
};

/** One row of the list: a cause, or a case in none, under the day it last moved. */
type Item = { kind: "group"; at: number; group: CaseGroup } | { kind: "case"; at: number; kept: EvalCase };

function Cases({ agent, show, openGroup, open, go }: { agent: string; show: Show; openGroup: string | null; open: string | null; go: (changes: Record<string, string>) => void }): ReactNode {
  const credentials = useCredentials();
  const [listed, setListed] = useState<Listed | null>(null);
  const [groups, setGroups] = useState<CaseGroup[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);
  const [search, setSearch] = useState("");
  const [clearing, setClearing] = useState(false);
  // A group decided whole changes its cases under the list: both are read again.
  const [round, setRound] = useState(0);

  useEffect(() => {
    let gone = false;
    Promise.all([readCases(credentials, agent), readGroups(credentials, agent)]).then(
      ([cases, grouped]) => {
        if (gone) return;
        setListed(cases);
        setGroups(grouped);
        setRefused(null);
      },
      (failed) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, round]);

  const decided = useCallback((kept: EvalCase): void => {
    setListed((was) => {
      if (was === null) return was;
      const cases = was.cases.some((one) => one.id === kept.id) ? was.cases.map((one) => (one.id === kept.id ? kept : one)) : [kept, ...was.cases];
      return { ...was, cases, pending: cases.filter((one) => one.status === "pending").length };
    });
  }, []);
  const changed = useCallback(
    (group: CaseGroup): void => {
      setGroups((was) => (was === null ? was : was.map((one) => (one.id === group.id ? group : one))));
      if (group.status === "pending") return;
      setRound((was) => was + 1);
      // Decided, it leaves the list: the page goes on to the next.
      go({ [GROUP]: "", [CASE]: "" });
    },
    [go],
  );

  const cases = listed?.cases ?? [];
  const everyAgent = agent === "";
  const typed = search.trim().toLowerCase();
  const these = (groups ?? []).filter((group) => group.status === show && (typed === "" || `${group.cause} ${group.judge}`.toLowerCase().includes(typed)));
  // A case a person kept from a call, or wrote, falls in no judge's group.
  const byHand = cases.filter((kept) => (kept.group ?? null) === null && kept.status === show && (typed === "" || `${kept.name} ${saidIn(kept.golden)[0] ?? ""}`.toLowerCase().includes(typed)));
  const counted = (status: Show): number => (groups ?? []).filter((group) => group.status === status).length + cases.filter((kept) => (kept.group ?? null) === null && kept.status === status).length;
  const read = listed !== null && groups !== null;
  const full = listed !== null && listed.pending >= listed.pendingAtMost;

  const one = open === null ? undefined : cases.find((kept) => kept.id === open);
  const asked = openGroup ?? one?.group ?? null;
  const group = asked === null ? undefined : (groups ?? []).find((each) => each.id === asked);
  // A case in a group opens over its group, in the panel; one in no group is the page.
  const inGroup = group === undefined ? undefined : one;
  const loose = group === undefined ? one : undefined;
  const groupId = group?.id ?? "";
  const closeCase = useCallback(() => go({ [CASE]: "", [GROUP]: groupId }), [go, groupId]);

  const addressOf = (name: typeof GROUP | typeof CASE, id: string): string => {
    const next = new URLSearchParams();
    if (agent !== "") next.set(AGENT, agent);
    if (show !== "pending") next.set(SHOW, show);
    next.set(name, id);
    return `?${next.toString()}`;
  };

  // A cause sits under the day of its newest call, the way a thread does in Calls.
  const newestOf = (each: CaseGroup): number => Math.max(each.since, ...cases.filter((kept) => kept.group === each.id).map((kept) => kept.created_at));
  const items: Item[] = [...these.map((each): Item => ({ kind: "group", at: newestOf(each), group: each })), ...byHand.map((kept): Item => ({ kind: "case", at: kept.created_at, kept }))];
  const days = daysOf(items);
  const toOpen = (item: Item): string => (item.kind === "group" ? addressOf(GROUP, item.group.id) : addressOf(CASE, item.kept.id));

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  const first = days[0]?.items[0];
  if (read && openGroup === null && open === null && first !== undefined) return <Navigate to={{ pathname: HOME, search: toOpen(first) }} replace />;

  /** Everything the list shows, dismissed with no reason given: the doors take one at a time, and one refused does not stop the rest. */
  const dismissAll = async (): Promise<void> => {
    setClearing(true);
    setRefused(null);
    const moves: (() => Promise<unknown>)[] = [...these.map((each) => () => decideGroup(credentials, each.id, { status: "dismissed" })), ...byHand.map((kept) => () => decideCase(credentials, kept.id, { status: "dismissed" }))];
    let missed = 0;
    let why = "";
    for (const move of moves) {
      try {
        await move();
      } catch (failed) {
        missed += 1;
        why = saidBy(failed);
      }
    }
    try {
      const [kept, grouped] = await Promise.all([readCases(credentials, agent), readGroups(credentials, agent)]);
      setListed(kept);
      setGroups(grouped);
      go({ [GROUP]: "", [CASE]: "" });
      if (missed > 0) setRefused(`${missed} could not be dismissed: ${why}`);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setClearing(false);
    }
  };

  const empty = read && these.length === 0 && byHand.length === 0;

  return (
    <>
      <PageHead open={loose?.name ?? group?.judge} />
      <div className="app-layout cs-layout">
        <aside className="app-list" aria-label="Cases">
          <div className="app-list-head">
            <span className="app-list-title">Cases</span>
            <span className="dash-quiet">{read ? these.length + byHand.length : ""}</span>
            <span className="cs-list-moves">
              {show === "pending" && items.length > 0 && (clearing ? <span className="dash-quiet">Dismissing…</span> : <ConfirmButton label="Dismiss all" asks={`Dismiss ${items.length}?`} danger onConfirm={() => void dismissAll()} />)}
              {!everyAgent && (
                <button type="button" className="app-button" onClick={() => setWriting(true)}>
                  New
                </button>
              )}
            </span>
          </div>
          <input className="app-input app-search" aria-label="Search cases" placeholder="Search cases" value={search} onChange={(event) => setSearch(event.target.value)} />
          <AgentPick agent={agent} onPick={(picked) => go({ [AGENT]: picked, [GROUP]: "", [CASE]: "" })} />
          <div className="dash-switch" role="group" aria-label="Which cases">
            {SHOWS.map((each) => (
              <button key={each.show} type="button" aria-pressed={each.show === show} className={each.show === show ? "dash-switch-on" : ""} onClick={() => go({ [SHOW]: each.show === "pending" ? "" : each.show, [GROUP]: "", [CASE]: "" })}>
                {each.name}
                {read && <span className="cs-count">{counted(each.show)}</span>}
              </button>
            ))}
          </div>
          <div className="app-rows">
            {days.map((day) => (
              <Fragment key={day.key}>
                <div className="cs-day">{dayName(day)}</div>
                {day.items.map((item) =>
                  item.kind === "group" ? (
                    <Link key={item.group.id} to={{ pathname: HOME, search: toOpen(item) }} aria-current={item.group.id === group?.id ? "true" : undefined} className={item.group.id === group?.id ? "app-row app-row-on" : "app-row"}>
                      <span className="app-row-top">
                        <span className="dash-clip">{item.group.cause}</span>
                        <span className="cs-item-count">{item.group.cases}</span>
                      </span>
                      <span className="app-row-under dash-clip">
                        {item.group.judge}
                        {everyAgent && ` · ${item.group.agent}`}
                      </span>
                    </Link>
                  ) : (
                    <Link key={item.kept.id} to={{ pathname: HOME, search: toOpen(item) }} aria-current={item.kept.id === loose?.id ? "true" : undefined} className={item.kept.id === loose?.id ? "app-row app-row-on" : "app-row"}>
                      <span className="app-row-top">
                        <span className="dash-clip">{saidIn(item.kept.golden)[0] ?? item.kept.name}</span>
                      </span>
                      <span className="app-row-under dash-clip">
                        {everyAgent ? `${item.kept.agent} · ` : ""}
                        {fromOf(item.kept)}
                      </span>
                    </Link>
                  ),
                )}
              </Fragment>
            ))}
            {empty && typed !== "" && <p className="dash-quiet app-none">Nothing by that name.</p>}
          </div>
        </aside>
        <div className="app-open">
          <div className="app-main">
            {full && <p className="cs-full">The inbox is full, at {listed.pendingAtMost} cases waiting. A call that breaks now is judged as ever and not kept, until you decide some of these.</p>}
            {refused !== null && <p className="app-refused">{refused}</p>}
            {!read && refused === null && <p className="dash-quiet">Reading the cases…</p>}
            {empty && typed === "" && group === undefined && loose === undefined && (
              <div className="dash-card cs-none">
                <span className="cs-none-title">{show === "pending" ? "All clear" : "Nothing here"}</span>
                <span className="dash-quiet">{NOTHING[show]}</span>
              </div>
            )}
            {group !== undefined && <Group key={group.id} group={group} cases={cases.filter((kept) => kept.group === group.id)} everyAgent={everyAgent} open={inGroup?.id ?? null} onOpen={(kept) => go({ [GROUP]: group.id, [CASE]: kept.id === inGroup?.id ? "" : kept.id })} onChanged={changed} />}
            {loose !== undefined && <CaseOpen key={loose.id} kept={loose} onDecided={decided} />}
            {read && !empty && group === undefined && loose === undefined && <p className="dash-quiet">Pick a case to read it here.</p>}
          </div>
        </div>
      </div>
      {inGroup !== undefined && !writing && <CasePanel key={inGroup.id} kept={inGroup} onDecided={decided} onClose={closeCase} />}
      {writing && (
        <GoldenFormPanel
          agent={agent}
          was={undefined}
          onSaved={(kept) => {
            decided(kept);
            setWriting(false);
            go({ [SHOW]: kept.status === "pending" ? "" : kept.status, [GROUP]: "", [CASE]: kept.id });
          }}
          onClose={() => setWriting(false)}
        />
      )}
    </>
  );
}

/** The address says whose cases (`?agent=`, none for every agent's), which ones (`?show=`, the waiting unless said) and what is open (`?group=`, `?case=`). */
export function CasesPage(): ReactNode {
  const [params, setParams] = useSearchParams();
  const go = useCallback(
    (changes: Record<string, string>): void => {
      setParams(
        (was) => {
          const next = new URLSearchParams(was);
          for (const [name, value] of Object.entries(changes)) {
            if (value === "") next.delete(name);
            else next.set(name, value);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  const agent = params.get(AGENT) ?? "";
  const asked = params.get(SHOW);
  const show: Show = asked === "approved" || asked === "dismissed" ? asked : "pending";
  // One page per agent in view: nothing read for one is ever drawn for another.
  return <Cases key={agent} agent={agent} show={show} openGroup={params.get(GROUP)} open={params.get(CASE)} go={go} />;
}
