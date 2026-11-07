/** The callers to choose from, as one select of many: chips of the chosen with their initials, as Personas draws them, and a search, opening a list of each caller — the agent's own first, then Pinecall's library and the ones switched off. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { Avatar, Icon, Pill, Select, SelectItem } from "../../ui";
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
    // Every agent in view: each agent's own callers ring it, Pinecall's library rings the one picked
    // — the ones switched on for it, or, none switched on yet, any of them, as with the agent in view.
    const library = ordered.filter(isPinecalls);
    const switchedOn = library.filter((persona) => persona.on);
    return [
      { title: "Written for your agents", personas: ordered.filter((persona) => !isPinecalls(persona)), rings: true },
      {
        title: switchedOn.length === 0 ? `Pinecall's callers · none switched on for ${agent} yet, any can still call` : `Pinecall's callers · ring ${agent}`,
        personas: all || switchedOn.length === 0 ? library : switchedOn,
        rings: false,
      },
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
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const typed = useRef<HTMLInputElement>(null);
  const asked = query.trim().toLowerCase();
  const matches = (persona: Persona): boolean => asked === "" || `${persona.name} ${aboutOf(persona)}`.toLowerCase().includes(asked);
  const groups = groupsOf(props)
    .map((group) => ({ ...group, personas: group.personas.filter(matches) }))
    .filter((group) => group.personas.length > 0);
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
    <div className="sim-callers">
      <div className="sim-pick" ref={box}>
        {/* The field: each caller chosen a chip with its face and a cross, then the search. */}
        <div
          className={open ? "sim-pick-field sim-pick-field-open" : "sim-pick-field"}
          onClick={() => {
            setOpen(true);
            typed.current?.focus();
          }}
        >
          {chosen.map((persona) => (
            <span key={keyOf(persona)} className="sim-pick-chip">
              <Avatar name={persona.name} size={20} round />
              {persona.name}
              <button
                type="button"
                className="sim-pick-unchip"
                aria-label={`Remove ${persona.name}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onPick(persona);
                }}
              >
                ×
              </button>
            </span>
          ))}
          {chosen.length === 0 && (
            <span className="sim-pick-lead" aria-hidden>
              <Icon name="users" size={15} />
            </span>
          )}
          <input
            ref={typed}
            className="sim-pick-search"
            value={query}
            placeholder={chosen.length === 0 ? "Choose who calls…" : "Add another…"}
            aria-label="Search the callers"
            onFocus={() => setOpen(true)}
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onKeyDown={(event) => {
              // Backspace on an empty search takes the last chip off, as select2 does.
              const last = chosen[chosen.length - 1];
              if (event.key === "Backspace" && query === "" && last !== undefined) onPick(last);
            }}
          />
          <Icon name="chevron" size={15} />
        </div>
        {open && (
          <div className="sim-pick-list" role="listbox" aria-multiselectable aria-label="Who calls">
            {groups.length === 0 && <p className="sim-pick-none">No caller matches “{query}”.</p>}
            {groups.map((group) => (
              <div key={group.title} className="sim-pick-group">
                <div className="sim-pick-title">{group.title}</div>
                {group.personas.map((persona) => (
                  <Row key={keyOf(persona)} persona={persona} rings={group.rings ? persona.agent : undefined} on={picked.has(keyOf(persona))} onPick={() => onPick(persona)} />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
      {library && agents.length > 1 && (
        <label className="sim-callers-ring">
          Pinecall&apos;s callers ring
          <Select size="sm" value={agent} onValueChange={onAgent} aria-label="The agent Pinecall's callers ring">
            {agents.map((one) => (
              <SelectItem key={one} value={one}>
                {one}
              </SelectItem>
            ))}
          </Select>
        </label>
      )}
    </div>
  );
}

// What a caller wants, in a line: Pinecall's own say it in their summary, a written one in its about.
function aboutOf(persona: Persona): string {
  return isPinecalls(persona) ? (persona.summary ?? persona.goal) : persona.about !== "" ? persona.about : persona.goal;
}

// One caller in the list: its face, its name and what it wants, ticked when chosen.
function Row({ persona, rings, on, onPick }: { persona: Persona; rings?: string | undefined; on: boolean; onPick: () => void }): ReactNode {
  return (
    <button type="button" role="option" aria-selected={on} className={on ? "sim-pick-row sim-pick-row-on" : "sim-pick-row"} onClick={onPick}>
      <Avatar name={persona.name} size={28} round />
      <span className="sim-pick-words">
        <span className="sim-pick-name">
          {persona.name}
          {rings !== undefined && <span className="sim-pick-rings">rings {rings}</span>}
          {persona.tags.includes("red-team") && (
            <Pill tone="red" small>
              red team
            </Pill>
          )}
        </span>
        <span className="sim-pick-about">{aboutOf(persona)}</span>
      </span>
      <span className="sim-pick-check" aria-hidden>
        {on && <Icon name="tick" size={11} />}
      </span>
    </button>
  );
}
