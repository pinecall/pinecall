/** A pick among a few named things drawn as chips, each with a quiet word beside it: whose key a vendor runs on, which model is the default. */

import type { ReactNode } from "react";

/** One chip: what is picked, the word shown, and what it says beside it. */
export interface Pick {
  value: string;
  label: ReactNode;
  /** Whether the label is a name a machine reads, drawn fixed-width. */
  mono?: boolean | undefined;
  /** Beside the label, quieter. */
  tag?: string | undefined;
}

export function Choice({ label, picks, value, onPick }: { label: string; picks: readonly Pick[]; value: string; onPick: (value: string) => void }): ReactNode {
  return (
    <div className="set-choice" role="radiogroup" aria-label={label}>
      {picks.map((one) => (
        <button key={one.value} type="button" role="radio" aria-checked={one.value === value} className={one.value === value ? "set-pick set-pick-on" : "set-pick"} onClick={() => onPick(one.value)}>
          <span className={one.mono === true ? "set-pick-mono" : undefined}>{one.label}</span>
          {one.tag !== undefined && one.tag !== "" && <span className="set-pick-tag">{one.tag}</span>}
        </button>
      ))}
    </div>
  );
}
