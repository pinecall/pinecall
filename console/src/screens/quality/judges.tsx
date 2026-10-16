/** Every judge a call meets at hang-up, as tiles: Pinecall's switched on or off, the org's own, and the agent in view's own — what each asks, how it answers, how it has held, and its drift where it is counted. */

import { useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Chips, Empty, Refused } from "../../ui";
import { BEFORE_DAYS, NOW_DAYS, type Drifted } from "./drift";
import type { HeldRate } from "./held-rates";
import { JudgeForm } from "./judge-form";
import { JudgeTile, type Standing } from "./judge-tile";
import { dropJudge, PINECALL, writeJudge, type JudgeRow, type Whose } from "./judges-door";
import { TryJudge } from "./try-judge";
import { useJudges } from "./use-judges";

const ON_THE_BILL = "Turning a judge on costs one eval per call, unless your judges run on your own key. N/A is never billed.";

type Show = "all" | "on" | "own";

const SHOWS: readonly { value: Show; label: string }[] = [
  { value: "all", label: "All" },
  { value: "on", label: "On" },
  { value: "own", label: "Yours" },
];

const shown = (judge: JudgeRow, show: Show): boolean => (show === "all" ? true : show === "on" ? judge.owner !== PINECALL || judge.on : judge.owner !== PINECALL);

/**
 * One list per level: the org's (Pinecall's as the org switched them, and the org's own) or the
 * agent's (the same, switched for it, the agent's switch winning, and its own). A judge of one's
 * own is written, edited and dropped at its own level and read from the other; Pinecall's are
 * switched, never dropped. The held-rate is over the newest judged calls the screen read; the
 * drift is a week against a month, drawn only when the process holding the agent counted it.
 */
export function Judges({ agent, rates, read, drifted }: { agent: string; rates: ReadonlyMap<string, HeldRate>; read: number; drifted: Drifted | null }): ReactNode {
  const whose: Whose = agent === "" ? null : agent;
  const listed = useJudges(whose);
  const credentials = useCredentials();
  const [editing, setEditing] = useState<JudgeRow | "new" | null>(null);
  const [show, setShow] = useState<Show>("all");
  const [trying, setTrying] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const drift = drifted === null ? null : new Map(drifted.drift.judges.map((judge) => [judge.judge, judge]));
  const standing: Standing = { rates, drift, threshold: drifted?.threshold ?? null };
  const judges = (listed.judges ?? []).filter((judge) => shown(judge, show));
  const owner = agent === "" ? "org" : agent;
  // The org's own first, what somebody here wrote, then the agent's own; Pinecall's library after
  // them in two: the ones that guard a call, to switch on first, then the ones that grade it.
  const groups: { title: string; rows: JudgeRow[] }[] = [
    { title: agent === "" ? "The org's own · asked of every agent" : "The org's own · written with every agent in view", rows: judges.filter((judge) => judge.owner === "org") },
    ...(agent === "" ? [] : [{ title: `${agent}'s own`, rows: judges.filter((judge) => judge.owner === agent) }]),
    {
      title: agent === "" ? "Recommended · guard every call, switched for every agent" : `Recommended · guard every call, switched for ${agent}`,
      rows: judges.filter((judge) => judge.owner === PINECALL && judge.recommended),
    },
    { title: "More from Pinecall · grade the call, when you want that signal", rows: judges.filter((judge) => judge.owner === PINECALL && !judge.recommended) },
  ];
  const saved = (rows: JudgeRow[]): void => {
    listed.setJudges(rows);
    setEditing(null);
  };
  const asked = async (change: () => Promise<JudgeRow[]>): Promise<void> => {
    setRefused(null);
    try {
      listed.setJudges(await change());
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    }
  };
  const tried = groups.flatMap((group) => group.rows).find((row) => row.name === trying);

  return (
    <section className="ui-tiles-block">
      <div className="qly-bar">
        <Chips options={SHOWS} value={show} onChange={setShow} />
        <span className="qly-bar-meta">{drift === null ? `held over the newest ${read} judged calls` : `held over the newest ${read} judged calls · drift: the last ${NOW_DAYS} days against the last ${BEFORE_DAYS}`}</span>
        <Button size="sm" onClick={() => setEditing("new")} disabled={editing !== null}>
          {agent === "" ? "New judge for every agent" : `New judge for ${agent}`}
        </Button>
      </div>
      <p className="qly-bill">{ON_THE_BILL}</p>
      {editing !== null && <JudgeForm whose={whose} agent={agent} editing={editing === "new" ? null : editing} onSaved={saved} onClose={() => setEditing(null)} />}
      <Refused>{listed.error ?? refused}</Refused>
      {groups.map((group) =>
        group.rows.length === 0 ? null : (
          <div key={group.title} className="ui-tiles-block">
            <h2 className="ui-tiles-title">{group.title}</h2>
            <div className="ui-tiles">
              {group.rows.map((row) => (
                <JudgeTile
                  key={row.name}
                  row={row}
                  mine={owner}
                  agent={agent}
                  standing={standing}
                  onSwitch={(on) => void asked(() => writeJudge(credentials, whose, row.name, { on }))}
                  onTry={() => setTrying(trying === row.name ? null : row.name)}
                  onEdit={() => setEditing(row)}
                  onDrop={() => void asked(() => dropJudge(credentials, whose, row.name))}
                />
              ))}
            </div>
          </div>
        ),
      )}
      {tried !== undefined && <TryJudge agent={agent} name={tried.name} written={null} />}
      {agent !== "" && listed.judges !== null && groups[2]?.rows.length === 0 && show !== "on" && editing === null && (
        <Empty>No judge of {agent}&apos;s own yet. The first one is one question: what a good call of this agent has to have done.</Empty>
      )}
    </section>
  );
}
