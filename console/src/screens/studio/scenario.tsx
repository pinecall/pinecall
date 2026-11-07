/** What a caller is about to phone about, read before the call: the goal a library caller was briefed with, or a persona's own, open to a last edit. */

import { useEffect, useState, type ReactNode } from "react";

import { Button, Icon } from "../../ui";
import { isPinecalls, type Persona } from "../personas/door";

/** A caller picked and what it phones about this run; `briefing` while the gateway writes it, `missed` when it could not. */
export interface Scenario {
  persona: Persona;
  goal: string;
  facts: Readonly<Record<string, string>>;
  briefing: boolean;
  /** Why the briefing did not come back; the caller then phones about its goal as written. */
  missed: string | null;
}

export function ScenarioCard({
  agent,
  scenario,
  voice,
  onCall,
  onAgain,
  onCancel,
}: {
  agent: string;
  scenario: Scenario;
  /** Out loud: the button says so. */
  voice: boolean;
  onCall: (goal: string) => void;
  /** Another briefing of the same caller; the library's alone. */
  onAgain: () => void;
  onCancel: () => void;
}): ReactNode {
  const { persona, briefing, missed } = scenario;
  const library = isPinecalls(persona);
  // The goal as the person leaves it: the briefing's words until they touch them, their own after.
  const [goal, setGoal] = useState(scenario.goal);
  useEffect(() => setGoal(scenario.goal), [scenario.goal]);
  const facts = Object.entries(scenario.facts);
  const ready = !briefing && goal.trim() !== "";
  return (
    <div className="sto-scenario" role="group" aria-label={`${persona.name} calls about`}>
      <div className="sto-scenario-top">
        <label className="sto-scenario-label" htmlFor="sto-scenario-goal">
          Calls about
        </label>
        <span className={missed === null ? "sto-scenario-tag" : "sto-scenario-tag sto-scenario-tag-off"} title={missed ?? undefined}>
          {briefing ? `reading ${agent}…` : missed !== null ? "not briefed · as written" : library ? `briefed on ${agent}` : "their own goal"}
        </span>
        <span className="sto-scenario-gap" />
        {library && (
          <button type="button" className="sto-scenario-icon" title="Another scenario" aria-label="Another scenario" disabled={briefing} onClick={onAgain}>
            <Icon name="refresh" size={14} />
          </button>
        )}
        <button type="button" className="sto-scenario-icon" title="Cancel" aria-label="Cancel" onClick={onCancel}>
          <Icon name="cross" size={14} />
        </button>
      </div>
      {briefing ? (
        <div className="sto-scenario-reading" aria-label={`Reading what ${agent} does`}>
          <span />
          <span />
        </div>
      ) : (
        <textarea id="sto-scenario-goal" className="sto-scenario-goal" rows={2} value={goal} placeholder="What they want, in their own words" spellCheck={false} onChange={(event) => setGoal(event.target.value)} />
      )}
      {facts.length > 0 && !briefing && (
        <div className="sto-scenario-facts" aria-label="Facts they know">
          {facts.map(([name, value]) => (
            <span key={name} className="sto-fact">
              <span className="sto-fact-name">{name}</span>
              {value}
            </span>
          ))}
        </div>
      )}
      <div className="sto-scenario-foot">
        <Button size="sm" kind="primary" disabled={!ready} onClick={() => onCall(goal.trim())}>
          <Icon name={voice ? "phone" : "chat"} size={14} />
          {voice ? `Call as ${persona.name}` : `Start as ${persona.name}`}
        </Button>
        <span className="sto-scenario-hint">{missed ?? "Edit it for this call alone"}</span>
      </div>
    </div>
  );
}
