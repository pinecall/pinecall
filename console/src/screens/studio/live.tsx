/** What production answers with, in the head: a word in the lede, and beside the save either Live or the move that deploys this release. */

import type { ReactNode } from "react";

import { Button, Icon } from "../../ui";
import type { StudioAgent } from "./door";

/** For the lede: where production stands against this release; nothing while it is read. */
export function productionSaid(release: number, production: StudioAgent | null | undefined): string {
  if (production === undefined) return "";
  if (production === null) return "not in production yet";
  return production.release === release ? "live in production" : `production answers with release ${String(production.release)}`;
}

export function Live({ release, production, busy, onDeploy }: { release: number; production: StudioAgent | null | undefined; busy: boolean; onDeploy: () => void }): ReactNode {
  if (production === undefined) return null;
  if (production !== null && production.release === release) {
    return (
      <span className="sto-live-on" title={`Production answers with release ${String(release)}`}>
        <Icon name="tick" size={14} />
        Live
      </span>
    );
  }
  return (
    <Button size="md" onClick={onDeploy} disabled={busy} title={production === null ? "Not in production yet" : `Production answers with release ${String(production.release)}`}>
      <Icon name="zap" size={14} />
      {busy ? "Deploying…" : `Deploy release ${String(release)}`}
    </Button>
  );
}
