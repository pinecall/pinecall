/** Whose settings a change lands on: in the sandbox a person's own or the team's, in production the one set there is. */

import type { ReactNode } from "react";

import { WORLD } from "../lib/world";

/** The corner a save lands on, and the settings it starts from: an empty personal corner runs on the team's. */
export function cornerOf<Row>(answer: { yours: Row | null; team: Row | null; production: Row | null }, team: boolean): { standing: Row | null; inEffect: Row | null } {
  if (WORLD === "production") return { standing: answer.production, inEffect: answer.production };
  const standing = team ? answer.team : answer.yours;
  return { standing, inEffect: standing ?? answer.team };
}

/** An app is set in its code, so the console only reads it. A Studio agent in production is what was deployed: it changes in the sandbox, then a deploy. */
export const readOnlyFor = (kind: "code" | "studio"): boolean => kind === "code" || WORLD === "production";

export function ReadOnlyNote({ kind }: { kind: "code" | "studio" }): ReactNode {
  if (kind === "code") {
    return (
      <p className="cfg-readonly" role="note">
        <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m16 18 6-6-6-6M8 6l-6 6 6 6" />
        </svg>
        Set in its code. Change it there and deploy.
      </p>
    );
  }
  return (
    <p className="cfg-readonly" role="note">
      <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="11" width="16" height="10" rx="2" />
        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
      </svg>
      Read-only in production. Edit it in Sandbox, then deploy.
    </p>
  );
}

export function CornerSwitch({ team, onChange }: { team: boolean; onChange: (team: boolean) => void }): ReactNode {
  if (WORLD !== "sandbox") return null;
  return (
    <div className="cfg-corner">
      <span className="dash-quiet">Changes apply to</span>
      <div className="dash-switch" role="group" aria-label="Changes apply to">
        <button type="button" aria-pressed={!team} className={team ? "" : "dash-switch-on"} onClick={() => onChange(false)}>
          Only you
        </button>
        <button type="button" aria-pressed={team} className={team ? "dash-switch-on" : ""} onClick={() => onChange(true)}>
          The team
        </button>
      </div>
    </div>
  );
}
