/** Studio's live preview: the Playground's conversation, beside the form, talking to the agent as it was last saved. */

import type { ReactNode } from "react";

import { Stage, useRoom } from "../talk";

export function Preview({ agent }: { agent: string }): ReactNode {
  const live = useRoom(agent);
  return (
    <aside className="sto-preview" aria-label="Preview">
      <div className="sto-preview-note">
        <strong>Preview</strong> · Saved changes answer on the next message.
      </div>
      <Stage agent={agent} live={live} />
    </aside>
  );
}
