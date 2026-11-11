/** Whose settings a change lands on: in the sandbox a person's own or the team's, in production the one set there is. */

import type { ReactNode } from "react";

import { WORLD } from "../lib/world";
import { Badge } from "../ui/setting";
import type { TuningAnswer, TuningBody } from "./door";

/** The corner a save lands on, and the settings it starts from: an empty personal corner runs on the team's. */
export function cornerOf<Row>(answer: { yours: Row | null; team: Row | null; production: Row | null }, team: boolean): { standing: Row | null; inEffect: Row | null } {
  if (WORLD === "production") return { standing: answer.production, inEffect: answer.production };
  const standing = team ? answer.team : answer.yours;
  return { standing, inEffect: standing ?? answer.team };
}

/** An agent's settings in one corner: what its next call runs, and what the corner itself set. */
export interface Tuned {
  /** What runs: the corner's own knobs over the team's, since each knob falls through on its own. */
  config: TuningBody;
  /** What the corner set itself: the only knobs a save writes back. */
  own: TuningBody;
  version: number | null;
}

export function tunedIn(answer: TuningAnswer, team: boolean): Tuned {
  const { standing } = cornerOf(answer, team);
  const own = standing?.config ?? {};
  const under = WORLD === "production" || team ? {} : (answer.team?.config ?? {});
  return { config: { ...under, ...own }, own, version: standing?.version ?? null };
}

/** The corner's next row: its own knobs with what was changed. A knob it only inherits, sent back as it was, stays inherited. */
export function nextRow(tuned: Tuned, changed: Partial<TuningBody>, drop: readonly (keyof TuningBody)[]): TuningBody {
  const next: Record<string, unknown> = { ...tuned.own };
  for (const [knob, value] of Object.entries(changed)) {
    const inherited = !(knob in tuned.own) && JSON.stringify(value) === JSON.stringify(tuned.config[knob as keyof TuningBody]);
    if (!inherited) next[knob] = value;
  }
  for (const knob of drop) delete next[knob];
  return next as TuningBody;
}

/** Whose word a setting is: the class's, a corner's, the organization's, or nobody's, which is Pinecall's default. */
export type From = "class" | "yours" | "team" | "production" | "organization" | "pinecall";

/** One knob as the next call reads it: the nearest corner that set it, since each knob falls through on its own. */
export function knobOf<Knob extends keyof TuningBody>(answer: TuningAnswer, knob: Knob): { value: NonNullable<TuningBody[Knob]> | null; from: From } {
  const corners: readonly (readonly [From, TuningAnswer["yours"]])[] = WORLD === "production" ? [["production", answer.production]] : [["yours", answer.yours], ["team", answer.team]];
  for (const [from, row] of corners) {
    const value = row?.config[knob];
    if (value !== null && value !== undefined) return { value, from };
  }
  return { value: null, from: "pinecall" };
}

/** Whose a value kept whole is, as a lexicon is: the corner's own, else the team's under it. */
export function wholeFrom<Row>(answer: { yours: Row | null; team: Row | null; production: Row | null }): From {
  if (WORLD === "production") return answer.production === null ? "pinecall" : "production";
  return answer.yours !== null ? "yours" : answer.team !== null ? "team" : "pinecall";
}

const ORIGINS: Record<From, { word: string; means: string }> = {
  class: { word: "Class", means: "Declared by the agent's class, which wins over every setting: change it in the code." },
  yours: { word: "Yours", means: "Set in your own corner of the sandbox: your calls run it, the team's do not." },
  team: { word: "Team", means: "Set for the whole team. Your corner sets nothing over it." },
  production: { word: "Production", means: "Set in production's own settings." },
  organization: { word: "Organization", means: "The organization's choice, for every agent that names none of its own." },
  pinecall: { word: "Default", means: "Nobody set it: this is what runs when the class, the agent and the organization say nothing." },
};

/** Whose word a setting is, as a badge that says so when pointed at. */
export function Origin({ from }: { from: From }): ReactNode {
  const { word, means } = ORIGINS[from];
  return (
    <span className="cfg-origin" title={means}>
      <Badge quiet={from !== "yours"}>{word}</Badge>
    </span>
  );
}

/** Production is what was deployed, so the console only reads it. Anywhere else each field is open unless its class declares it (`fixed`). */
export const READ_ONLY: boolean = WORLD === "production";

export function ReadOnlyNote({ kind }: { kind: "code" | "studio" }): ReactNode {
  return (
    <p className="cfg-readonly" role="note">
      <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="11" width="16" height="10" rx="2" />
        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
      </svg>
      {kind === "code" ? "Read-only in production." : "Read-only in production. Edit it in Sandbox, then deploy."}
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
