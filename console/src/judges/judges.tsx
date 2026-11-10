/** Judges, the same page as Agents and Simulations: every question a call is asked at hang-up in a list, Pinecall's switched and one's own written, beside the one open. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, useSearchParams, type To } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { percent } from "../lib/format";
import { useOrg } from "../lib/org";
import { toneOf } from "../quality/rules";
import { useScores } from "../quality/use-scores";
import { PageHead } from "../shell/page-head";
import { AgentPick } from "../ui/agent-pick";
import { Creature } from "./creature";
import { dropJudge, readAgreement, readJudges, writeJudge, type Calibration, type JudgeRow } from "./door";
import { groupsOf, heldBy, isOurs, isSwitched, SHOWS, type Held, type Show } from "./fold";
import { JudgeActions, JudgeView } from "./judge";
import { JudgeForm } from "./judge-form";
import { Judging } from "./judging";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
import "../quality/quality.css";
import "./judges.css";

const HOME = "/judges";
const AGENT = "agent";
const JUDGE = "judge";

/** One judge in the list: its name, how it held, and what it is there for. A switch left off reads quiet. */
function Item({ judge, held, open, to }: { judge: JudgeRow; held: Held | undefined; open: boolean; to: To }): ReactNode {
  const share = held === undefined || held.settled === 0 ? null : held.held / held.settled;
  const quiet = isSwitched(judge) && !judge.on;
  return (
    <Link to={to} aria-current={open ? "true" : undefined} className={`${open ? "app-row app-row-on" : "app-row"} jd-item${quiet ? " jd-item-off" : ""}`}>
      <Creature name={judge.name} size={28} />
      <span className="jd-item-words">
        <span className="app-row-top">
          <span className="dash-clip">{judge.name}</span>
          {share !== null && <span className={`jd-item-held ql-tone-${toneOf(share)}`}>{percent(share)}</span>}
        </span>
        <span className="app-row-under dash-clip">{judge.why ?? judge.summary ?? judge.question}</span>
      </span>
    </Link>
  );
}

function Judges({ agent, open, ask }: { agent: string; open: string | null; ask: (name: string, value: string) => void }): ReactNode {
  const credentials = useCredentials();
  const { lines } = useOrg();
  const [judges, setJudges] = useState<JudgeRow[] | null>(null);
  const [agreement, setAgreement] = useState<Calibration | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [show, setShow] = useState<Show>("all");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  // The form open: on a judge already written, or on a new one.
  const [writing, setWriting] = useState<JudgeRow | "new" | null>(null);

  useEffect(() => {
    let gone = false;
    readJudges(credentials, agent).then(
      (read) => !gone && setJudges(read),
      (failed) => !gone && setRefused(saidBy(failed)),
    );
    // The judges are drawn without their agreement when the door refuses it.
    readAgreement(credentials, agent).then(
      (read) => !gone && setAgreement(read),
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  const mine = useMemo(() => (agent === "" ? lines : lines.filter((line) => line.agent === agent)), [lines, agent]);
  const scored = useScores(mine);
  const held = useMemo(() => heldBy(scored), [scored]);
  const read = scored.filter((row) => row.score !== null && row.score.judges.length > 0).length;
  const close = useCallback(() => ask(JUDGE, ""), [ask]);

  const change = async (doing: () => Promise<JudgeRow[]>): Promise<boolean> => {
    setBusy(true);
    setRefused(null);
    try {
      setJudges(await doing());
      return true;
    } catch (failed) {
      setRefused(saidBy(failed));
      return false;
    } finally {
      setBusy(false);
    }
  };
  const turn = (judge: JudgeRow, on: boolean): void => void change(() => writeJudge(credentials, agent, judge.name, { on }));

  const groups = groupsOf(judges ?? [], agent, show, search);
  const one = open === null ? undefined : judges?.find((judge) => judge.name === open);
  const inCode = (judges ?? []).some((judge) => judge.fixed === true);
  const count = groups.reduce((total, group) => total + group.judges.length, 0);
  const addressOf = (name: string): string => {
    const next = new URLSearchParams();
    if (agent !== "") next.set(AGENT, agent);
    next.set(JUDGE, name);
    return `?${next.toString()}`;
  };

  // The menu's row names the page, and the page opens on the first of its list, in the address like any other.
  const first = groups[0]?.judges[0];
  if (open === null && first !== undefined) return <Navigate to={{ pathname: HOME, search: addressOf(first.name) }} replace />;

  return (
    <>
      <PageHead open={one?.name}>
        {agent === "" && <Judging />}
        {one !== undefined && isOurs(one, agent) && (
          <JudgeActions
            onEdit={() => setWriting(one)}
            onDrop={() => {
              void change(() => dropJudge(credentials, agent, one.name)).then((dropped) => dropped && close());
            }}
          />
        )}
      </PageHead>
      <div className="app-layout jd-layout">
        <aside className="app-list" aria-label="Judges">
          <div className="app-list-head">
            <span className="app-list-title">Judges</span>
            <span className="dash-quiet">{judges === null ? "" : count}</span>
            {!inCode && (
              <button type="button" className="app-button jd-small" onClick={() => setWriting("new")}>
                New
              </button>
            )}
          </div>
          <input className="app-input app-search" aria-label="Search judges" placeholder="Search judges" value={search} onChange={(event) => setSearch(event.target.value)} />
          <AgentPick agent={agent} onPick={(picked) => ask(AGENT, picked)} />
          <div className="dash-switch" role="group" aria-label="Which judges">
            {SHOWS.map((each) => (
              <button key={each.show} type="button" aria-pressed={each.show === show} className={each.show === show ? "dash-switch-on" : ""} onClick={() => setShow(each.show)}>
                {each.name}
              </button>
            ))}
          </div>
          {inCode && (
            <p className="dash-quiet jd-list-note" title="Its own are written beside its class, and so is which of Pinecall's its calls meet. Your org's own judges meet its calls on top.">
              Set in {agent}'s code
            </p>
          )}
          <div className="app-rows">
            {groups.flatMap((group) => [
              <span key={group.title} className="jd-shelf" title={group.about}>
                {group.title}
              </span>,
              ...group.judges.map((judge) => <Item key={judge.name} judge={judge} held={held.get(judge.name)} open={judge.name === one?.name} to={{ pathname: HOME, search: addressOf(judge.name) }} />),
            ])}
            {judges !== null && groups.length === 0 && <p className="dash-quiet app-none">{search.trim() !== "" ? "No judge by that name." : show === "own" ? "You have written no judge yet." : "No judge is on."}</p>}
          </div>
        </aside>
        <div className="app-open">
          <div className="app-main">
            {refused !== null && <p className="app-refused">{refused}</p>}
            {judges === null && refused === null && <p className="dash-quiet">Reading the judges…</p>}
            {one !== undefined && <JudgeView key={one.name} judge={one} agent={agent} held={held.get(one.name)} read={read} agreement={agreement} busy={busy} onSwitch={(to) => turn(one, to)} />}
            {judges !== null && one === undefined && groups.length > 0 && <p className="dash-quiet">Pick a judge to read it here.</p>}
          </div>
        </div>
      </div>
      {writing !== null && (
        <JudgeForm
          agent={agent}
          was={writing === "new" ? null : writing}
          onSaved={(kept, name) => {
            setJudges(kept);
            setWriting(null);
            ask(JUDGE, name);
          }}
          onClose={() => setWriting(null)}
        />
      )}
    </>
  );
}

/** The address says whose judges (`?agent=`, none for the org's) and which one is open (`?judge=`). */
export function JudgesPage(): ReactNode {
  const [params, setParams] = useSearchParams();
  const ask = useCallback(
    (name: string, value: string): void => {
      setParams(
        (was) => {
          const next = new URLSearchParams(was);
          if (value === "") next.delete(name);
          else next.set(name, value);
          // Another agent's list may not hold the judge that was open.
          if (name === AGENT) next.delete(JUDGE);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  const agent = params.get(AGENT) ?? "";
  // One page per agent in view: nothing read for one is ever drawn for another.
  return <Judges key={agent} agent={agent} open={params.get(JUDGE)} ask={ask} />;
}
