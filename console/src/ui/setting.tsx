/** The pieces of a settings form: a titled field, a row with an icon and a sentence, a switch, a slider with its number, a badge, a vendor's mark. */

import type { ReactNode } from "react";

import { Icon, type IconName } from "../shell/icons";
import "./ui.css";

export function Field({ label, children }: { label: string; children: ReactNode }): ReactNode {
  return (
    <div className="ui-field">
      <span className="ui-field-label">{label}</span>
      {children}
    </div>
  );
}

/** One setting: its icon, name and sentence, the control under them, or at their right when `aside` is given. */
export function Setting({ icon, title, about, aside, children }: { icon: IconName; title: string; about: ReactNode; aside?: ReactNode; children?: ReactNode }): ReactNode {
  return (
    <div className="ui-setting">
      <span className="ui-setting-icon">
        <Icon name={icon} size={17} />
      </span>
      <div className="ui-setting-main">
        <div className="ui-setting-top">
          <div className="ui-setting-words">
            <span className="ui-setting-title">{title}</span>
            <p className="ui-setting-about">{about}</p>
          </div>
          {aside}
        </div>
        {children}
      </div>
    </div>
  );
}

export function Toggle({ on, label, disabled = false, onChange }: { on: boolean; label: string; disabled?: boolean | undefined; onChange: (on: boolean) => void }): ReactNode {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} className={on ? "ui-toggle ui-toggle-on" : "ui-toggle"} onClick={() => onChange(!on)} />;
}

/** A slider and the number it moves; an empty number is "not set", with the slider resting at `rest`. */
export function Slider({ value, label, min, max, step, rest, ends, disabled = false, onChange }: { value: string; label: string; min: number; max: number; step: number; rest: number; ends?: readonly [string, string] | undefined; disabled?: boolean | undefined; onChange: (value: string) => void }): ReactNode {
  return (
    <div className="ui-slider">
      <div className="ui-slider-track">
        <input type="range" aria-label={`${label} slider`} min={min} max={max} step={step} disabled={disabled} value={value === "" ? rest : Number(value)} onChange={(event) => onChange(event.target.value)} />
        {ends !== undefined && (
          <span className="ui-slider-ends">
            <span>{ends[0]}</span>
            <span>{ends[1]}</span>
          </span>
        )}
      </div>
      <input className="cfg-input ui-slider-number" type="number" aria-label={label} min={min} max={max} step={step} placeholder="Default" disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

export function Badge({ quiet = false, children }: { quiet?: boolean; children: ReactNode }): ReactNode {
  return <span className={quiet ? "ui-badge ui-badge-quiet" : "ui-badge"}>{children}</span>;
}

/** A tile with a letter, where a brand's logo would go. */
export function Mark({ letter }: { letter: string }): ReactNode {
  return (
    <span className="ui-mark" aria-hidden="true">
      {letter.toUpperCase()}
    </span>
  );
}

/** A bar that shows or folds what follows it. */
export function Fold({ title, open, onToggle }: { title: string; open: boolean; onToggle: () => void }): ReactNode {
  return (
    <button type="button" className="ui-fold" aria-expanded={open} onClick={onToggle}>
      {title}
      <span>
        <Icon name="chevron" size={15} />
      </span>
    </button>
  );
}
