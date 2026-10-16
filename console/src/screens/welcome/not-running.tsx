/** What a step says when no agent of the org's is running: what that takes, in order, and the way back to the step that does it. */

import type { ReactNode } from "react";

import { Button } from "../../ui";
import { Command } from "./command";

export function NotRunning({ doing, onBack }: { doing: string; onBack: () => void }): ReactNode {
  return (
    <div className="wel-block">
      <strong>Nothing is running yet</strong>
      <span className="wel-hint">{doing} needs your agent up on your computer. In order, that is:</span>
      <ol className="wel-needs">
        <li>the CLI installed, and this computer signed in to your org</li>
        <li>the project written and linked: linking is what gives it its key</li>
        <li>
          <code className="wel-inline">pinecall start</code> left running in the project's folder
        </li>
      </ol>
      <div className="wel-line">
        <Button size="sm" onClick={onBack}>
          Back to the step that does this
        </Button>
        <span className="wel-hint">This page notices by itself once it is up.</span>
      </div>
      <Command line="pinecall start" say="once the project exists, from its folder" />
    </div>
  );
}
