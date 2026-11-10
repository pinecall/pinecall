/** Who is signed in, at the sidebar's foot, and what is theirs on any page: the theme and signing out. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { initialsOf } from "@pinecall/core/initials";
import { chooseTheme, currentTheme, watchTheme } from "@pinecall/core/theme";
import { useOrg } from "../lib/org";
import { Icon } from "./icons";
import { useAway } from "./use-away";

export function Me({ onLeave }: { onLeave: () => void }): ReactNode {
  const { whose, orgs } = useOrg();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState(currentTheme);
  const held = useAway(open, useCallback(() => setOpen(false), []));
  const name = whose?.name ?? whose?.subject ?? "…";
  const role = orgs?.find((one) => one.here)?.role ?? "";

  useEffect(() => watchTheme(() => setTheme(currentTheme())), []);

  return (
    <div className="sh-me-held" ref={held}>
      <button type="button" className="sh-me-who" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="sh-me-mark" aria-hidden="true">
          {initialsOf(name)}
        </span>
        <span className="sh-words">
          <span className="sh-strong">{name}</span>
          <span className="sh-under">{role}</span>
        </span>
      </button>
      {open && (
        <div className="sh-me-menu" role="menu" aria-label={name}>
          <button type="button" role="menuitem" className="sh-org-row" onClick={() => setTheme(chooseTheme(theme === "dark" ? "light" : "dark"))}>
            <Icon name={theme === "dark" ? "sun" : "moon"} size={15} />
            <span className="sh-words">
              <span className="sh-strong">{theme === "dark" ? "Light theme" : "Dark theme"}</span>
            </span>
          </button>
          <button type="button" role="menuitem" className="sh-org-row" onClick={onLeave}>
            <Icon name="leave" size={15} />
            <span className="sh-words">
              <span className="sh-strong">Sign out</span>
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
