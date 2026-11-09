/** Who calls: the agent's callers as tiles to tick, its own first, with a search once there are many; comparing, each says how many things it holds the agent to. */

import { useState, type ReactNode } from "react";

import { initialsOf } from "@pinecall/core/initials";
import { Icon } from "../shell/icons";
import { aboutOf, inOrder, isPinecalls, type Persona } from "./door";

// Past this many a person looks for a caller by name rather than by eye.
const A_SCREENFUL = 8;

export function Callers({ callers, picked, onPick, one, goals = false }: { callers: readonly Persona[]; picked: ReadonlySet<string>; onPick: (name: string) => void; one: boolean; goals?: boolean }): ReactNode {
  const [typed, setTyped] = useState("");
  const [all, setAll] = useState(false);
  const ordered = inOrder(callers);
  // Pinecall's library switched off stays folded until asked for, unless nothing else can call.
  const ready = ordered.filter((caller) => !isPinecalls(caller) || caller.on);
  const offered = all || ready.length === 0 ? ordered : ready;
  const asked = typed.trim().toLowerCase();
  const shown = offered.filter((caller) => asked === "" || `${caller.name} ${aboutOf(caller)}`.toLowerCase().includes(asked));
  const folded = ordered.length - ready.length;

  return (
    <div className="sim-callers">
      {offered.length > A_SCREENFUL && <input className="app-input sim-search" aria-label="Search callers" placeholder="Search callers" value={typed} onChange={(event) => setTyped(event.target.value)} />}
      <div className="sim-tiles" role={one ? "radiogroup" : "group"} aria-label="Who calls">
        {shown.map((caller) => {
          const on = picked.has(caller.name);
          return (
            <button key={caller.name} type="button" role={one ? "radio" : "checkbox"} aria-checked={on} className={on ? "sim-tile sim-tile-on" : "sim-tile"} onClick={() => onPick(caller.name)}>
              <span className="sim-face" aria-hidden="true">
                {on ? <Icon name="check" size={15} /> : initialsOf(caller.name)}
              </span>
              <span className="sim-tile-words">
                <span className="sim-tile-name">
                  <span className="dash-clip">{caller.name}</span>
                  {caller.tags.includes("red-team") && <span className="sim-red">Red team</span>}
                </span>
                <span className="sim-tile-about">{aboutOf(caller)}</span>
                {goals && <span className={caller.expects.length === 0 ? "sim-checks sim-checks-none" : "sim-checks"}>{caller.expects.length === 0 ? "Expects nothing: only the platform's judges" : `${caller.expects.length} ${caller.expects.length === 1 ? "thing" : "things"} the agent must do`}</span>}
              </span>
            </button>
          );
        })}
      </div>
      {shown.length === 0 && asked !== "" && <p className="dash-quiet">No caller by that name.</p>}
      {folded > 0 && ready.length > 0 && (
        <button type="button" className="sim-link" onClick={() => setAll(!all)}>
          {all ? "Show only the ones switched on" : `Show ${folded} more from Pinecall's library`}
        </button>
      )}
    </div>
  );
}
