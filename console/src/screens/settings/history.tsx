/** A corner's versions, newest first, with author, reason and diff. */

import type { ReactNode } from "react";

import { type TuningHistory } from "@pinecall/core/wire/rest-org";

import { dayAndTime } from "../../lib/format";
import { Button, Card, CardHead, Empty } from "../../ui";
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
                <b>v{row.version}</b>
                <span className="ui-cell-faint">
                  {row.author} · {dayAndTime(row.set_at)}
                </span>
                {row.note !== null && <span className="set-version-note">“{row.note}”</span>}
                {canRollBack && at > 0 && (
                  <Button size="xs" onClick={() => void onRollBack(row.version)}>
                    Roll back to this
                  </Button>
                )}
              </div>
              {changed.length > 0 && <div className="set-version-changes">{changed.join(" · ")}</div>}
            </div>
          );
        })
      )}
    </Card>
  );
}
