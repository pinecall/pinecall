/** The callers to choose from, as one select of many: a field that shows who will call, opening a list of each caller's name and what it is about — the agent's own, Pinecall's library and the ones switched off. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { Icon, Pill, Select, SelectItem } from "../../ui";
import { isPinecalls, type Persona } from "../personas/door";

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

/** A heading of the list and the callers under it; `rings` says whom each rings when that is not the one agent. */
interface Group {
  title: string;
  personas: Persona[];
  rings: boolean;
}

function groupsOf({ inView, agent, personas, all }: CallersProps): Group[] {
  const ordered = inOrder(personas);
  if (inView === "") {
    // Every agent in view: each agent's own callers ring it, Pinecall's library rings the one picked.
    return [
      { title: "Written for your agents", personas: ordered.filter((persona) => !isPinecalls(persona)), rings: true },
      { title: `Pinecall's callers · ring ${agent}`, personas: ordered.filter((persona) => isPinecalls(persona) && (all || persona.on)), rings: false },
    ];
  }
  const on = ordered.filter(isOn);
  const off = ordered.filter((persona) => !isOn(persona));
  return [
    { title: `Ready to call ${agent}`, personas: on, rings: false },
    { title: on.length === 0 ? "Pinecall's callers · none switched on yet, any can still call" : "Switched off · called by hand", personas: all || on.length === 0 ? off : [], rings: false },
  ];
}

export function Callers(props: CallersProps): ReactNode {
  const { inView, agents, agent, onAgent, personas, picked, onPick } = props;
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const groups = groupsOf(props).filter((group) => group.personas.length > 0);
  const chosen = inOrder(personas).filter((persona) => picked.has(keyOf(persona)));

  // Open, the list closes on a click anywhere else and on Escape, as a select's menu does.
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent): void => {
      if (box.current !== null && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const library = inView === "" && personas.some(isPinecalls);
  return (
    <div className="sim-menu">
      <div className="sim-menu-pick" ref={box}>
        <button type="button" className={open ? "sim-menu-field sim-menu-field-open" : "sim-menu-field"} aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
          {chosen.length === 0 ? (
            <span className="sim-menu-empty">Choose who calls…</span>
          ) : (
            <span className="sim-menu-said">{saidOf(chosen)}</span>
          )}
          <Icon name="chevron" size={15} />
        </button>
        {open && (
          <div className="sim-menu-list" role="listbox" aria-multiselectable aria-label="Who calls">
            {groups.map((group) => (
              <div key={group.title} className="sim-menu-group">
                <div className="sim-menu-title">{group.title}</div>
                {group.personas.map((persona) => (
                  <Row key={keyOf(persona)} persona={persona} rings={group.rings ? persona.agent : undefined} on={picked.has(keyOf(persona))} onPick={() => onPick(persona)} />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
      {library && agents.length > 1 && (
        <span className="sim-menu-ring">
          Pinecall&apos;s callers ring
          <Select size="sm" value={agent} onValueChange={onAgent} aria-label="The agent Pinecall's callers ring">
            {agents.map((one) => (
              <SelectItem key={one} value={one}>
                {one}
              </SelectItem>
            ))}
          </Select>
        </span>
      )}
    </div>
  );
}

// Who will call, in the field: two names, or two and how many more.
function saidOf(chosen: readonly Persona[]): string {
  const [first, second] = chosen;
  if (second === undefined) return first?.name ?? "";
  return chosen.length === 2 ? `${first!.name} and ${second.name}` : `${first!.name}, ${second.name} and ${String(chosen.length - 2)} more`;
}

function Row({ persona, rings, on, onPick }: { persona: Persona; rings?: string | undefined; on: boolean; onPick: () => void }): ReactNode {
  return (
    <button type="button" role="option" aria-selected={on} className={on ? "sim-menu-row sim-menu-row-on" : "sim-menu-row"} onClick={onPick}>
      <span className="sim-menu-check" aria-hidden>
        {on && <Icon name="tick" size={11} />}
      </span>
      <span className="sim-menu-words">
        <span className="sim-menu-name">
          {persona.name}
          {rings !== undefined && <span className="sim-menu-rings">rings {rings}</span>}
          {persona.tags.includes("red-team") && (
            <Pill tone="red" small>
              red-team
            </Pill>
          )}
        </span>
        {persona.about !== "" && <span className="sim-menu-about">{persona.about}</span>}
      </span>
    </button>
  );
}
