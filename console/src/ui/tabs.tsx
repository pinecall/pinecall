/** Underlined page tabs with the active one in the accent color. */

import type { ReactNode } from "react";

export interface TabItem<T extends string> {
  tab: T;
  name: string;
  /** Shown after the name, e.g. a dot or count. */
  mark?: ReactNode | undefined;
}

/** Tab row. The screen owns the active tab, usually in the URL. */
export function Tabs<T extends string>({
  label,
  tabs,
  on,
  onPick,
}: {
  label: string;
  tabs: readonly TabItem<T>[];
  on: T;
  onPick: (tab: T) => void;
}): ReactNode {
  return (
    <nav className="ui-tabs" aria-label={label}>
      {tabs.map((one) => (
        <button
          key={one.tab}
          type="button"
          className={on === one.tab ? "ui-tab ui-tab-on" : "ui-tab"}
          aria-current={on === one.tab ? "page" : undefined}
          onClick={() => onPick(one.tab)}
        >
          {one.name}
          {one.mark}
        </button>
      ))}
    </nav>
  );
}
