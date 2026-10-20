/** A corner's versions, newest first, with author, reason and diff. */

import type { ReactNode } from "react";

import { type TuningHistory } from "@pinecall/core/wire/rest-org";

import { dayAndTime } from "../../lib/format";
import { Card, CardHead, Empty } from "../../ui";
import { changes } from "./door";

export function History({
  kept,
  canRollBack,
  onRollBack,
}: {
  kept: TuningHistory | null;
  canRollBack: boolean;
  onRollBack: (version: number) => Promise<void>;
}): ReactNode {
  return (
    <Card>
      <CardHead title="History" meta={kept === null ? undefined : kept.holder === "" ? "the org's own corner" : `corner ${kept.holder}`} />
      {kept === null ? (
        <Empty>Asking the gateway…</Empty>
      ) : kept.rows.length === 0 ? (
        <Empty>Nothing set in this corner yet: the next call runs on what the corner falls back to.</Empty>
      ) : (
        kept.rows.map((row, at) => {
          const older = kept.rows[at + 1];
          const changed = changes(older?.config ?? {}, row.config);
          return (
            <div key={row.version} className="set-version">
              <div className="set-version-head">
                <span className="set-version-chip">v{row.version}</span>
                <span className="set-version-who">
                  {row.author} · {dayAndTime(row.set_at)}
                </span>
                {at === 0 ? (
                  <span className="set-version-now">in force</span>
                ) : (
                  canRollBack && (
                    <button type="button" className="set-version-back" onClick={() => void onRollBack(row.version)}>
                      Roll back
                    </button>
                  )
                )}
              </div>
              {row.note !== null && <span className="set-version-note">“{row.note}”</span>}
              {changed.length > 0 && <div className="set-version-changes">{changed.join(" · ")}</div>}
            </div>
          );
        })
      )}
    </Card>
  );
}
