/** Settings sidebar: the current config of one corner, a field per line. */

import { useState, type ReactNode } from "react";

import { type TuningAnswer, type TuningRow } from "@pinecall/core/wire/rest-org";

import { dayAndTime } from "../../lib/format";
import { Card, CardHead, Segmented } from "../../ui";
import { FIELDS, LABEL, shown } from "./door";

export type Corner = "yours" | "team" | "production";

const NAMES: Record<Corner, string> = { yours: "Yours", team: "Team", production: "Production" };

/**
 * One corner at a time: the sandbox switches between yours, team and production; production shows
 * only its own. Unset fields show the fallback value.
 */
export function Now({ answer, corners, first }: { answer: TuningAnswer; corners: readonly Corner[]; first: Corner }): ReactNode {
  const [corner, setCorner] = useState<Corner>(first);
  const row = answer[corner];
  return (
    <Card>
      <CardHead title="What is set now" meta={answer.world} />
      {corners.length > 1 && (
        <div className="set-now-pick">
          <Segmented options={corners.map((one) => ({ value: one, label: NAMES[one] }))} value={corner} onChange={setCorner} />
        </div>
      )}
      <dl className="set-now">
        {FIELDS.map((field) => (
          <div key={field} className="set-now-row">
            <dt>{LABEL[field]}</dt>
            <dd className={value(row, field, corner) === FALLS_BACK[corner] ? "set-now-none" : undefined}>{value(row, field, corner)}</dd>
          </div>
        ))}
      </dl>
      <div className="set-now-foot">{row === null ? "Nothing saved in this corner yet." : versionLine(row)}</div>
    </Card>
  );
}

// Fallback per corner: yours → team's; the others → runtime default.
const FALLS_BACK: Record<Corner, string> = { yours: "the team's", team: "—", production: "—" };

function value(row: TuningRow | null, field: (typeof FIELDS)[number], corner: Corner): string {
  if (row === null) return FALLS_BACK[corner];
  return shown(row.config, field) ?? FALLS_BACK[corner];
}

function versionLine(row: TuningRow): string {
  return `v${row.version} · ${row.author} · ${dayAndTime(row.set_at)}${row.note === null ? "" : ` · “${row.note}”`}`;
}
