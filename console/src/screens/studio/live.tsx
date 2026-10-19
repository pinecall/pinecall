/** What production answers with, under the chat: the release it holds, whether it is the one in the sandbox, and the move that makes it so. */

import type { ReactNode } from "react";

import { Icon } from "../../ui";
import type { StudioAgent } from "./door";

export function Live({ release, dirty, production, busy, onDeploy }: { release: number; dirty: boolean; production: StudioAgent | null | undefined; busy: boolean; onDeploy: () => void }): ReactNode {
  const same = production !== null && production !== undefined && production.release === release;
  const title = production === undefined ? "Reading production…" : production === null ? "Not in production yet" : `Production answers with release ${String(production.release)}`;
  const under =
    production === undefined
      ? ""
      : production === null
        ? `Deploy release ${String(release)} to answer there`
        : same
          ? dirty
            ? "Same as the last save; the changes on this page are not in it"
            : "Same as the sandbox"
          : `Release ${String(release)} is not live yet`;
  return (
    <div className="sto-live">
      <span className="sto-live-words">
        <span className="sto-live-title">{title}</span>
        {under !== "" && <span className="sto-live-under">{under}</span>}
      </span>
      {same ? (
        <span className="sto-live-on">
          <Icon name="tick" size={14} />
          Live
        </span>
      ) : (
        production !== undefined && (
          <button type="button" className="sto-live-deploy" disabled={busy} onClick={onDeploy}>
            {busy ? "Deploying…" : `Deploy release ${String(release)}`}
          </button>
        )
      )}
    </div>
  );
}
