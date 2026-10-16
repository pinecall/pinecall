/** The top bar: where you are — whose calls, which screen — on the left; the notices, the theme and the way out on the right. */

import type { ReactNode } from "react";
import { useLocation } from "react-router";

import { useLeaving } from "../lib/leaving";
import { AGENT_SCREENS, BOX_SCREENS, ORG_SCREENS, rowOf, screenAt, tabName } from "../lib/mode";
import { NoticesButton } from "./notices-button";
import { ThemeButton } from "./theme-button";

/** The page's title, from the path: the row's name, and its tab's after it where the screen is one. */
export function titleOf(pathname: string, agent: string): string {
  const segments = pathname.split("/").filter(Boolean);
  if (segments[0] === "cli") return "Sign in a terminal";
  if (segments[0] === "box") {
    const box = BOX_SCREENS.find((one) => one.path === `box/${segments[1] ?? ""}`);
    return box === undefined ? "Box" : box.key === "box-orgs" && segments[2] !== undefined ? "Organization" : box.name;
  }
  const screen = screenAt(pathname);
  if (screen === undefined) return "Overview";
  const row = rowOf(agent === "" ? ORG_SCREENS : AGENT_SCREENS, screen);
  const name = screen.key === "numbers" ? "Phone numbers" : screen.name;
  return row.key === screen.key ? name : `${row.name} · ${tabName(screen)}`;
}

export function Top({ agent }: { agent: string }): ReactNode {
  const leave = useLeaving();
  const { pathname } = useLocation();
  const screen = screenAt(pathname);
  // Whose calls the screen is about: the agent in view, every agent, or — the box's, the
  // workspace's and the person's own screens, which are nobody's calls — nothing at all.
  const row = screen === undefined ? undefined : rowOf(ORG_SCREENS, screen);
  const nobodys = row === undefined || row.group === "workspace" || row.group === "yours";
  const whose = pathname.startsWith("/box/") ? "Box" : agent !== "" ? agent : nobodys ? null : "All agents";
  return (
    <header className="top">
      {whose !== null && <span className="top-crumb">{whose}</span>}
      {whose !== null && <span className="top-sep">/</span>}
      <span className="top-title">{titleOf(pathname, agent)}</span>
      <div className="top-right">
        <NoticesButton />
        <ThemeButton />
        {/* Both consoles are the box's and both hold a key of this browser's, so both sign out. */}
        <button type="button" className="top-leave" onClick={leave}>
          Sign out
        </button>
      </div>
    </header>
  );
}
