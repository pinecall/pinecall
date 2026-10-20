/** The agent's head, as every page's: its name and release, then another agent, its code to take, production, and the save. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { Button, Icon, PageHead } from "../../ui";

export function Head({
  name,
  sub,
  busy,
  downloading,
  saving,
  canSave,
  live,
  onDownload,
  onSave,
}: {
  name: string;
  /** Under the name: the release, who saved it and when. */
  sub: string;
  busy: boolean;
  downloading: boolean;
  saving: boolean;
  canSave: boolean;
  /** Where production stands, beside the save: Live, or the deploy. */
  live: ReactNode;
  onDownload: () => void;
  onSave: () => void;
}): ReactNode {
  return (
    <PageHead
      title={name}
      lede={sub}
      actions={
        <>
          {/* Another agent is made from Studio with no agent in view: this opens the form there. */}
          {/* The two seldom moves are icons, so the head stays one row beside the name. */}
          <Link to="/studio?new=1" className="ui-button sto-square" title="New agent" aria-label="New agent">
            <Icon name="plug" size={15} />
          </Link>
          <Button size="md" className="sto-square" onClick={onDownload} disabled={busy} title={downloading ? "Downloading…" : "Download code"} aria-label="Download code">
            <Icon name="download" size={15} />
          </Button>
          {live}
          <Button size="md" kind="primary" onClick={onSave} disabled={busy || !canSave}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </>
      }
    />
  );
}
