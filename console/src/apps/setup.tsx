/** An app's setup: what its calls run on. What its class declares is locked here; the rest edits in the side panel. */

import type { ReactNode } from "react";

import { AdvancedTab } from "../advanced/advanced";
import { Configure } from "../configure/configure";
import { KnowledgeTab } from "../configure/knowledge";

const nothing = (): void => undefined;

export function Setup({ agent }: { agent: string }): ReactNode {
  return (
    <div className="app-setup">
      <Configure agent={agent} kind="code" onSaved={nothing} />
      <section className="dash-card" aria-label="Knowledge">
        <KnowledgeTab agent={agent} />
      </section>
      <AdvancedTab agent={agent} kind="code" />
    </div>
  );
}
