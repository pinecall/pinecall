/** The agent a model writes personas for, asked in the side panel when the page shows every agent. */

import { useState, type ReactNode } from "react";

import { Select } from "../ui/select";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";

export function AskAgent({ title, about, agents, onPick, onClose }: { title: string; about: string; agents: readonly string[]; onPick: (agent: string) => void; onClose: () => void }): ReactNode {
  const [agent, setAgent] = useState(agents[0] ?? "");
  return (
    <SidePanel
      title={title}
      icon="personas"
      about={about}
      onClose={onClose}
      footer={
        <div className="cfg-dialog-foot">
          <button type="button" className="app-button" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="cfg-save" disabled={agent === ""} onClick={() => onPick(agent)}>
            Continue
          </button>
        </div>
      }
    >
      <Field label="Which agent">
        <Select label="Which agent" value={agent} items={agents.map((slug) => ({ value: slug, label: slug }))} onChange={setAgent} />
      </Field>
    </SidePanel>
  );
}
