/** The filters the list and the table share: the kind of conversation, the tests switch, the four status chips with their counts, and the agent when the org has several. */

import type { ReactNode } from "react";

import { type SessionLine } from "@pinecall/core/wire/rest";
import { useOrg } from "../lib/org";
import { Select } from "../ui/select";
import { keeps, STATUSES } from "./status";
import { TYPES, type CallsUrl } from "./url";

/** `lines` are the calls in view, before the status: each chip counts what it would keep. */
export function StatusChips({ lines, url }: { lines: readonly SessionLine[]; url: CallsUrl }): ReactNode {
  return (
    <div className="calls-chips" role="group" aria-label="Which calls">
      {STATUSES.map((one) => {
        const count = lines.filter((line) => keeps(one.value, line)).length;
        const on = url.status === one.value;
        return (
          <button key={one.value} type="button" className={on ? "calls-chip calls-chip-on" : "calls-chip"} aria-pressed={on} onClick={() => url.ask("status", one.value)}>
            {one.name}
            <span className={one.value === "asking" && count > 0 ? "calls-chip-count calls-chip-count-warm" : "calls-chip-count"}>{count}</span>
          </button>
        );
      })}
    </div>
  );
}

// One picker, always showing what is picked: the kinds do not fit as chips, and a panel would hide the choice.
/** Which kind of conversation is listed, and whether simulations and golden runs are listed with the real ones. */
export function TypePick({ url }: { url: CallsUrl }): ReactNode {
  return (
    <div className="calls-types">
      <div className="calls-pick">
        <Select label="Showing" value={url.type} items={TYPES.map((one) => ({ value: one.value, label: one.value === "" ? "Showing: everything" : one.label }))} onChange={(value) => url.ask("type", value)} />
      </div>
      <label className="calls-tests" title="Simulated callers and golden runs are tests, not people: they are listed only when this is on">
        <input type="checkbox" checked={url.tests} onChange={(event) => url.ask("tests", event.target.checked ? "1" : "")} />
        Tests
      </label>
    </div>
  );
}

/** Nothing when the org has one agent. Calls from agents nobody holds any more stay filterable: their calls happened. */
export function AgentPick({ url }: { url: CallsUrl }): ReactNode {
  const { agents, lines } = useOrg();
  const slugs = [...new Set([...agents.map((one) => one.slug), ...lines.map((line) => line.agent)])].sort();
  if (slugs.length < 2) return null;
  return (
    <div className="calls-pick">
      <Select label="Filter by agent" value={url.agent} items={[{ value: "", label: "Every agent" }, ...slugs.map((slug) => ({ value: slug, label: slug }))]} onChange={(value) => url.ask("agent", value)} />
    </div>
  );
}
