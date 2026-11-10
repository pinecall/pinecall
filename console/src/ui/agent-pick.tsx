/** The agent a page of the whole org narrows to, picked in its header; drawn only when the org has more than one. */

import type { ReactNode } from "react";

import { useOrg } from "../lib/org";
import { Select } from "./select";
import "./ui.css";

/** "" is every agent. Agents nobody holds any more stay pickable: their calls happened. */
export function AgentPick({ agent, onPick }: { agent: string; onPick: (agent: string) => void }): ReactNode {
  const { agents, lines } = useOrg();
  const slugs = [...new Set([...agents.map((one) => one.slug), ...lines.map((line) => line.agent), ...(agent === "" ? [] : [agent])])].sort();
  if (slugs.length < 2) return null;
  return (
    <div className="ui-agent-pick">
      <Select label="Whose" value={agent} items={[{ value: "", label: "Every agent" }, ...slugs.map((slug) => ({ value: slug, label: slug }))]} onChange={onPick} />
    </div>
  );
}
