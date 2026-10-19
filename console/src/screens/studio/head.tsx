/** The agent's head: who it is and which release, the way to its voice and models, its code to take, and the save. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { Button, Icon } from "../../ui";

export function Head({
  name,
  sub,
  busy,
  downloading,
  saving,
  canSave,
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
  onDownload: () => void;
  onSave: () => void;
}): ReactNode {
  return (
    <div className="sto-head">
      <span className="sto-head-icon" aria-hidden>
        <Icon name="bot" size={22} />
      </span>
      <span className="sto-head-words">
        <span className="sto-head-name">{name}</span>
        <span className="sto-head-sub">{sub}</span>
      </span>
      {/* Its voice and the models it thinks and listens with are Configure's: the voice is picked there by ear. */}
      <Link to={`/a/${encodeURIComponent(name)}/configure?stage=speaks`} className="sto-head-link">
        <Icon name="sliders" size={14} />
        Voice &amp; models
      </Link>
      {/* Another agent is made from Studio with no agent in view: this link opens the form there. */}
      <Link to="/studio?new=1" className="sto-head-link">
        <Icon name="plug" size={14} />
        New agent
      </Link>
      <Button size="md" onClick={onDownload} disabled={busy}>
        <Icon name="download" size={14} />
        {downloading ? "Downloading…" : "Download code"}
      </Button>
      <Button size="md" kind="primary" onClick={onSave} disabled={busy || !canSave}>
        {saving ? "Saving…" : "Save"}
      </Button>
    </div>
  );
}
