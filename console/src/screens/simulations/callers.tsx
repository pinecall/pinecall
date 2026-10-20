/** The callers to choose from, as compact cards that are ticked — a name, and whom it rings: the agent's own, Pinecall's library and the ones switched off. */

import type { ReactNode } from "react";

import { Icon, Pill, Select, SelectItem } from "../../ui";
import { isPinecalls, type Persona } from "../personas/door";
import { Face } from "../personas/face";

/** What picks a caller out: its owner, the agent it was written for, and its name. */
export function keyOf(persona: Persona): string {
  return `${isPinecalls(persona) ? "pinecall" : persona.agent}/${persona.name}`;
}

// The callers a person has enabled: the ones written for the agent, and Pinecall's it switched on.
function isOn(persona: Persona): boolean {
  return !isPinecalls(persona) || persona.on;
}

// The agent's own first, the ones somebody wrote for it; Pinecall's library after them, realism before the red team.
export function inOrder(personas: Persona[]): Persona[] {
  const own = personas.filter((persona) => !isPinecalls(persona));
  const red = (persona: Persona): number => Number(persona.tags.includes("red-team"));
  const library = personas.filter(isPinecalls).sort((one, other) => red(one) - red(other) || one.name.localeCompare(other.name));
  return [...own, ...library];
}

export interface CallersProps {
  /** The agent in view, or "" for every agent: with one in view, the agent is it. */
  inView: string;
  /** The agents a caller may be put on: the ones a process holds right now. */
  agents: readonly string[];
  /** The agent Pinecall's callers ring: the one in view, else the one picked beside the library. */
  agent: string;
  onAgent: (agent: string) => void;
  personas: Persona[];
  /** The keys ticked. */
  picked: ReadonlySet<string>;
  onPick: (persona: Persona) => void;
  /** The switched-off callers are listed too. */
  all: boolean;
}

export function Callers({ inView, agents, agent, onAgent, personas, picked, onPick, all }: CallersProps): ReactNode {
  const ordered = inOrder(personas);
  const card = (persona: Persona, rings?: string): ReactNode => <Caller key={keyOf(persona)} persona={persona} rings={rings} on={picked.has(keyOf(persona))} onPick={() => onPick(persona)} />;
  if (inView === "") {
    // Every agent in view: each agent's own callers ring it, Pinecall's library rings the one picked.
    const own = ordered.filter((persona) => !isPinecalls(persona));
    const library = ordered.filter((persona) => isPinecalls(persona) && (all || persona.on));
    return (
      <>
        {own.length > 0 && <Group title="Written for your agents · each rings its own">{own.map((persona) => card(persona, persona.agent))}</Group>}
        {library.length > 0 && (
          <Group
            title={
              <span className="sim-group-pick">
                Pinecall&apos;s callers · ring
                {agents.length > 1 ? (
                  <Select size="sm" value={agent} onValueChange={onAgent} aria-label="The agent Pinecall's callers ring">
                    {agents.map((one) => (
                      <SelectItem key={one} value={one}>
                        {one}
                      </SelectItem>
                    ))}
                  </Select>
                ) : (
                  agent
                )}
              </span>
            }
          >
            {library.map((persona) => card(persona))}
          </Group>
        )}
      </>
    );
  }
  const on = ordered.filter(isOn);
  const off = ordered.filter((persona) => !isOn(persona));
  return (
    <>
      {on.length > 0 && <Group title={`Ready to call ${agent}`}>{on.map((persona) => card(persona))}</Group>}
      {(all || on.length === 0) && off.length > 0 && (
        <Group title={on.length === 0 ? `Pinecall's callers · none is switched on for ${agent} yet, and any of them can still call it` : `Switched off for ${agent} · called by hand`}>{off.map((persona) => card(persona))}</Group>
      )}
    </>
  );
}

function Group({ title, children }: { title: ReactNode; children: ReactNode }): ReactNode {
  return (
    <div className="sim-group">
      <div className="sim-group-title">{title}</div>
      <div className="sim-callers">{children}</div>
    </div>
  );
}

function Caller({ persona, rings, on, onPick }: { persona: Persona; rings?: string | undefined; on: boolean; onPick: () => void }): ReactNode {
  const classes = ["sim-caller", on ? "sim-caller-on" : null, isOn(persona) ? null : "sim-caller-off"];
  return (
    <button type="button" className={classes.filter((one) => one !== null).join(" ")} aria-pressed={on} onClick={onPick}>
      <Face name={persona.name} size={32} />
      <span className="sim-caller-words">
        <span className="sim-caller-name">
          {persona.name}
          {persona.tags.includes("red-team") && (
            <Pill tone="red" small>
              red-team
            </Pill>
          )}
        </span>
        {rings !== undefined && <span className="sim-caller-rings">rings {rings}</span>}
      </span>
      <span className="sim-caller-check" aria-hidden>
        {on && <Icon name="tick" size={11} />}
      </span>
    </button>
  );
}
