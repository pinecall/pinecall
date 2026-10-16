/** A select: a trigger that reads like a field, and a menu drawn by the page in its own palette — Radix underneath. */

import * as Radix from "@radix-ui/react-select";
import type { ReactNode } from "react";

// Radix keeps "" for "nothing chosen" and refuses it as an item's value, while the console's
// selects use "" for exactly that choice — "Every agent", "Choose a number…". So "" is carried as
// this word inside the menu and handed back as "" outside it: a caller never sees the difference.
const NONE = "\u0000none";

const inside = (value: string): string => (value === "" ? NONE : value);
const outside = (value: string): string => (value === NONE ? "" : value);

export function Select({
  value,
  onValueChange,
  size = "form",
  disabled,
  required,
  defaultOpen,
  onOpenChange,
  placeholder,
  id,
  className,
  children,
  "aria-label": label,
}: {
  value: string;
  onValueChange: (value: string) => void;
  size?: "sm" | "form" | undefined;
  disabled?: boolean | undefined;
  required?: boolean | undefined;
  /** Opened the moment it is drawn: a value edited in place, in a row. */
  defaultOpen?: boolean | undefined;
  /** Told when the menu opens and closes — closed without a pick is an edit given up. */
  onOpenChange?: ((open: boolean) => void) | undefined;
  /** Written in the trigger while the value matches no item. */
  placeholder?: string | undefined;
  id?: string | undefined;
  className?: string | undefined;
  /** The items: one `SelectItem` each. */
  children: ReactNode;
  "aria-label"?: string | undefined;
}): ReactNode {
  const classes = ["ui-select"];
  if (size === "sm") classes.push("ui-select-sm");
  if (className !== undefined) classes.push(className);
  return (
    <Radix.Root
      // "" reaches Radix as itself when a placeholder is to be written for it; else as the sentinel an item may carry.
      value={placeholder !== undefined && value === "" ? "" : inside(value)}
      onValueChange={(chosen) => onValueChange(outside(chosen))}
      {...(disabled === undefined ? {} : { disabled })}
      {...(required === undefined ? {} : { required })}
      {...(defaultOpen === undefined ? {} : { defaultOpen })}
      {...(onOpenChange === undefined ? {} : { onOpenChange })}
    >
      <Radix.Trigger id={id} className={classes.join(" ")} aria-label={label}>
        <span className="ui-select-value">
          <Radix.Value placeholder={placeholder} />
        </span>
        <Radix.Icon className="ui-select-chevron">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="m6 9 6 6 6-6" />
          </svg>
        </Radix.Icon>
      </Radix.Trigger>
      <Radix.Portal>
        <Radix.Content className="ui-select-menu" position="popper" sideOffset={6} collisionPadding={12}>
          <Radix.ScrollUpButton className="ui-select-scroll">▴</Radix.ScrollUpButton>
          <Radix.Viewport className="ui-select-viewport">{children}</Radix.Viewport>
          <Radix.ScrollDownButton className="ui-select-scroll">▾</Radix.ScrollDownButton>
        </Radix.Content>
      </Radix.Portal>
    </Radix.Root>
  );
}

/** One choice in a select's menu: its value, and what the menu and the trigger write for it. */
export function SelectItem({ value, disabled, children }: { value: string; disabled?: boolean | undefined; children: ReactNode }): ReactNode {
  return (
    <Radix.Item value={inside(value)} {...(disabled === undefined ? {} : { disabled })} className="ui-select-item">
      <Radix.ItemText>{children}</Radix.ItemText>
      <Radix.ItemIndicator className="ui-select-check">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="m5 12.5 4.5 4.5L19 7.5" />
        </svg>
      </Radix.ItemIndicator>
    </Radix.Item>
  );
}
