/** Prompt panel: the app's prompt blocks, their status, and the running cost. */

import { type Cost } from "@pinecall/core/wire/defs";
import { type PromptState } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";

import { usd } from "../../lib/format";
import { KV, SectionLabel } from "../../ui";

export function PromptPanel({ prompt, cost }: { prompt: PromptState; cost: Cost | null }): ReactNode {
  const blocks = Object.entries(prompt);
  return (
    <>
      <SectionLabel ruled>Prompt</SectionLabel>
      <div className="call-pane-body call-pane-body-tight">
        {blocks.length === 0 && <div className="call-sub">The app has written no block yet.</div>}
        {blocks.map(([name, block]) => (
          <div key={name} className="call-prompt-row">
            <span className="call-prompt-name">{name}</span>
            <span className="call-prompt-hash" title={block.hash}>
              {block.hash.slice(0, 8)}
            </span>
            <span className="call-prompt-chars">{block.chars.toLocaleString("en").replace(/,/g, " ")} chars</span>
          </div>
        ))}
        {cost !== null && <KV label="cost so far">{usd(cost.usd)}</KV>}
      </div>
    </>
  );
}
