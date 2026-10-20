/** What most people never touch, folded under one word at the foot of a stage until it is asked for. */

import { useState, type ReactNode } from "react";

import { Icon } from "../../ui";

export function Advanced({ children }: { children: ReactNode }): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <div className="set-advanced">
      <button type="button" className="set-advanced-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className={open ? "set-caret set-caret-open" : "set-caret"}>
          <Icon name="chevron" size={13} />
        </span>
        Advanced
      </button>
      {open && <div className="set-advanced-body">{children}</div>}
    </div>
  );
}
