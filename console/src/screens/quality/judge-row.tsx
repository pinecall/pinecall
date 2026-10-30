/** One judge as a row: its creature, its question, how it answers and when, how it has held, how far it is trusted — and what to do with it. */

import type { ReactNode } from "react";

import { percent } from "../../lib/format";
import { Pill, Switch, TableRow, TextAction } from "../../ui";
import { BEFORE_DAYS, NOW_DAYS, type JudgeDrift } from "./drift";
import type { HeldRate } from "./held-rates";
import { Creature } from "./creature";
import { answersOf, readsOf, whenOf } from "./judge-words";
import { PINECALL, type JudgeRow } from "./judges-door";
import type { Agreement } from "./use-agreement";

/** Where the drift columns are: what a row is drawn with, and what each verdict is read against. */
export interface Standing {
  rates: ReadonlyMap<string, HeldRate>;
  drift: ReadonlyMap<string, JudgeDrift> | null;
  threshold: number | null;
  /** Each judge against the labels people gave; null until read. */
  agreement: Agreement | null;
}

/** The columns a judge's row and its head share. */
export const JUDGE_COLUMNS = "minmax(0, 2.4fr) minmax(0, 1.1fr) minmax(170px, auto) 170px";

export function JudgeLine({
  row,
  mine,
  agent,
  standing,
  onSwitch,
  onTry,
  onEdit,
  onDrop,
}: {
  row: JudgeRow;
  /** The owner whose judges this level writes: "org", or the agent's slug. */
  mine: string;
  /** The agent in view, or "" for every agent: a judge is tried on an agent's calls. */
  agent: string;
  standing: Standing;
  onSwitch: (on: boolean) => void;
  onTry: () => void;
  onEdit: () => void;
  onDrop: () => void;
}): ReactNode {
  const library = row.owner === PINECALL;
  // A row the class declares is read here, never written: its file, or its switch in the class.
  const ours = row.owner === mine && row.fixed !== true;
  const theClasss = row.owner === "class";
  // A library judge says first what it saves you from; any other, the question it asks.
  const said = library ? (row.why ?? row.summary ?? row.question) : row.question;
  const reads = readsOf(row);
  return (
    <TableRow columns={JUDGE_COLUMNS}>
      <span className={library && !row.on ? "qly-jrow-who qly-jrow-off" : "qly-jrow-who"}>
        <Creature name={row.name} size={36} />
        <span className="qly-jrow-words">
          <span className="qly-jrow-name">
            {row.name}
            {!library && (
              <Pill tone="violet" small>
                {row.owner === "org" ? "the org's" : theClasss ? "the class's" : "yours"}
              </Pill>
            )}
          </span>
          <span className="qly-jrow-said" title={said}>
            {said}
          </span>
        </span>
      </span>
      <span className="qly-jrow-how">
        <span>{answersOf(row)}</span>
        <span className="qly-jrow-faint" title={whenOf(row)}>
          {whenOf(row)}
          {reads === "" ? "" : ` · reads ${reads}`}
        </span>
      </span>
      <span className="qly-jrow-stand">
        <Standings name={row.name} standing={standing} />
      </span>
      <span className="qly-jrow-moves">
        {agent !== "" && <TextAction onClick={onTry}>Try</TextAction>}
        {ours && <TextAction onClick={onEdit}>Edit</TextAction>}
        {ours && (
          <TextAction danger onClick={onDrop}>
            Drop
          </TextAction>
        )}
        {library && row.fixed !== true && <Switch on={row.on} label={`${row.name} on`} onChange={onSwitch} />}
        {library && row.fixed === true && <span className="qly-jrow-faint">{row.on ? "on" : "off"} · the class&apos;s</span>}
      </span>
    </TableRow>
  );
}

/** A judge's held-rate, or its two windows and the move between them where the drift is counted; then how far it is trusted. */
function Standings({ name, standing }: { name: string; standing: Standing }): ReactNode {
  const agreed = standing.agreement === null ? null : <Agreed name={name} agreement={standing.agreement} />;
  if (standing.drift === null) {
    return (
      <>
        <Labelled label="held">
          <Held rate={standing.rates.get(name)} />
        </Labelled>
        {agreed}
      </>
    );
  }
  const judged = standing.drift.get(name);
  return (
    <>
      <Labelled label={`${NOW_DAYS} days`}>
        <Window standing={judged?.now ?? null} />
      </Labelled>
      <Labelled label={`${BEFORE_DAYS} days`}>
        <Window standing={judged?.before ?? null} faint />
      </Labelled>
      <Labelled label="drift">
        <Drift delta={judged?.delta ?? null} threshold={standing.threshold} />
      </Labelled>
      {agreed}
    </>
  );
}

/** How often the judge agreed with the labels people gave: the rate over the compared labels, coloured once it is judged untrusted. */
function Agreed({ name, agreement }: { name: string; agreement: Agreement }): ReactNode {
  const judged = agreement.judges.get(name);
  if (judged === undefined || judged.rate === null) {
    return (
      <Labelled label="agrees">
        <span className="qly-rate ui-cell-faint" title="Nobody labelled this judge yet: dismissing a case says whether it was wrong.">
          —
        </span>
      </Labelled>
    );
  }
  const title =
    judged.trusted === null
      ? `${agreement.labelsToJudge - judged.compared} more labels to compare before it is judged`
      : judged.trusted
        ? `trusted: it agreed with ${percent(agreement.agreesAtLeast)} of its labels at least`
        : `untrusted: it agreed with fewer than ${percent(agreement.agreesAtLeast)} of its labels`;
  return (
    <Labelled label={judged.trusted === false ? "agrees · untrusted" : "agrees"}>
      <span className="qly-rate" title={title}>
        <span className={judged.trusted === false ? "qly-pct qly-pct-bad" : "qly-pct"}>{percent(judged.rate)}</span>
        <span className="ui-cell-faint">
          {judged.agreed}/{judged.compared}
        </span>
      </span>
    </Labelled>
  );
}

function Labelled({ label, children }: { label: string; children: ReactNode }): ReactNode {
  return (
    <span className="qly-stand">
      <span className="qly-stand-label">{label}</span>
      {children}
    </span>
  );
}

/** A held-rate as a cell: the percent and the count under it, or a dash where nothing settled. */
function Held({ rate }: { rate: HeldRate | undefined }): ReactNode {
  if (rate === undefined || rate.settled === 0) return <span className="qly-rate ui-cell-faint">—</span>;
  return (
    <span className="qly-rate">
      <span className={rate.held === rate.settled ? "qly-pct" : "qly-pct qly-pct-bad"}>{percent(rate.held / rate.settled)}</span>
      <span className="ui-cell-faint">
        {rate.held}/{rate.settled}
      </span>
    </span>
  );
}

/** One window of the drift: the percent, or a dash where no verdict fell in it — never a zero. */
function Window({ standing, faint = false }: { standing: JudgeDrift["now"]; faint?: boolean }): ReactNode {
  if (standing === null) return <span className="qly-rate ui-cell-faint">—</span>;
  return (
    <span className="qly-rate">
      <span className={faint ? "qly-pct qly-pct-faint" : "qly-pct"}>{standing.percent.toFixed(0)}%</span>
      <span className="ui-cell-faint">
        {standing.held}/{standing.settled}
      </span>
    </span>
  );
}

/** The move between the windows; only a drop past the threshold is coloured, because it is the one to act on. */
function Drift({ delta, threshold }: { delta: number | null; threshold: number | null }): ReactNode {
  if (delta === null) return <span className="qly-rate ui-cell-faint">—</span>;
  const falling = threshold !== null && delta < -Math.abs(threshold);
  return <span className={falling ? "qly-rate qly-drift-bad" : "qly-rate ui-cell-faint"}>{`${delta > 0 ? "+" : delta < 0 ? "−" : "±"}${Math.abs(delta).toFixed(0)} pts`}</span>;
}
