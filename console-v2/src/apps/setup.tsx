/** An app's setup: what its calls run on, read off the gateway. An app is set in its code, so it is read here and changed there. */

import type { ReactNode } from "react";

import { Configure } from "../configure/configure";
import { KnowledgeTab } from "../configure/knowledge";

const nothing = (): void => undefined;

export function Setup({ agent }: { agent: string }): ReactNode {
  return (
    <div className="app-setup">
      <Configure agent={agent} kind="code" onSaved={nothing} />
      <section className="dash-card" aria-label="Knowledge">
        <KnowledgeTab agent={agent} kind="code" />
      </section>
    </div>
  );
}
