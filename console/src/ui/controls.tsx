/** The controls: buttons, the labelled field, the segmented choice, filter chips, a switch. */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { Link } from "react-router";

export type ButtonKind = "secondary" | "primary" | "dashed" | "danger";
/** xs 28 · sm 30 · md 32 · base 34 · form 36 · lg 42 (full width) */
export type ButtonSize = "xs" | "sm" | "md" | "base" | "form" | "lg";

function buttonClass(kind: ButtonKind, size: ButtonSize, pill: boolean, extra?: string): string {
  const classes = ["ui-button"];
  if (kind !== "secondary") classes.push(`ui-button-${kind}`);
  if (size !== "base") classes.push(`ui-button-${size}`);
  if (pill) classes.push("ui-button-pill");
  if (extra !== undefined) classes.push(extra);
  return classes.join(" ");
}

export function Button({
  kind = "secondary",
  size = "base",
  pill = false,
  className,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { kind?: ButtonKind | undefined; size?: ButtonSize; pill?: boolean | undefined }): ReactNode {
  return <button type={type} className={buttonClass(kind, size, pill, className)} {...rest} />;
}

/** A button that goes somewhere. */
export function ButtonLink({
  to,
  kind = "secondary",
  size = "base",
  children,
}: {
  to: string;
  kind?: ButtonKind | undefined;
  size?: ButtonSize | undefined;
  children: ReactNode;
}): ReactNode {
  return (
    <Link to={to} className={buttonClass(kind, size, false)}>
      {children}
    </Link>
  );
}

/** The quiet action at the end of a row: Revoke, Drop, Remove. */
export function TextAction({
  danger = false,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean | undefined }): ReactNode {
  return <button type="button" className={danger ? "ui-text-action ui-text-action-danger" : "ui-text-action"} {...rest} />;
}

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string | undefined }): ReactNode {
  return (
    <label className="ui-label" htmlFor={htmlFor}>
      {children}
    </label>
  );
}

export function Input({
  size = "form",
  className,
  ...rest
}: Omit<InputHTMLAttributes<HTMLInputElement>, "size"> & { size?: "sm" | "form" | "lg" | undefined }): ReactNode {
  const classes = ["ui-input"];
  if (size === "sm") classes.push("ui-input-sm");
  if (size === "lg") classes.push("ui-input-lg");
  if (className !== undefined) classes.push(className);
  return <input className={classes.join(" ")} {...rest} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>): ReactNode {
  return <textarea className="ui-textarea" {...props} />;
}

/** A label over its control, taking the room it is given. */
export function Field({
  label,
  grow = false,
  minWidth,
  children,
}: {
  label: ReactNode;
  grow?: boolean | undefined;
  minWidth?: number | undefined;
  children: ReactNode;
}): ReactNode {
  return (
    <div className={grow ? "ui-form-grow" : undefined} style={minWidth === undefined ? undefined : { minWidth }}>
      <label className="ui-label">{label}</label>
      {children}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: readonly { value: T; label: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
}): ReactNode {
  return (
    <div className="ui-segmented" role="group">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={option.value === value ? "ui-segment ui-segment-on" : "ui-segment"}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Round filter chips: the providers' kinds, the calls' corners. */
export function Chips<T extends string>({
  options,
  value,
  onChange,
}: {
  options: readonly { value: T; label: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
}): ReactNode {
  return (
    <div className="ui-chips" role="group">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={option.value === value ? "ui-chip ui-chip-on" : "ui-chip"}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Switch({ on, onChange, label }: { on: boolean; onChange: (on: boolean) => void; label: string }): ReactNode {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={on ? "ui-switch ui-switch-on" : "ui-switch"}
      onClick={() => onChange(!on)}
    >
      <span className="ui-switch-knob" />
    </button>
  );
}

export function Check({ checked, onChange, children }: { checked: boolean; onChange: (checked: boolean) => void; children: ReactNode }): ReactNode {
  return (
    <label className="ui-check">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {children}
    </label>
  );
}
