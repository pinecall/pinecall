/** The tab bar over a screen: the row it belongs to and every tab of that row this key opens, off the one table. */

import type { ReactNode } from "react";
import { Navigate, NavLink, useLocation, useParams } from "react-router";

import { opens } from "@pinecall/core/scopes";
import { AGENT_SCREENS, BOX_SCREENS, ORG_SCREENS, rowOf, screenAt, tabName, tabsOf, type Screen } from "../lib/mode";
import { useScopes } from "../lib/whoami";

/**
 * Drawn only where a row has more than one screen this key opens: Settings, an agent's Test.
 * A row of one screen has nothing to switch and gets no bar. Which tab is on is the URL's, so a
 * link lands on it and a reload keeps it — the same rule every `?view=` on the page follows.
 */
export function ScreenTabs({ agent }: { agent: string }): ReactNode {
  const scopes = useScopes();
  const { pathname } = useLocation();
  const table = agent === "" ? [...ORG_SCREENS, ...BOX_SCREENS] : AGENT_SCREENS;
  const at = screenAt(pathname);
  if (at === undefined) return null;
  const row = rowOf(table, at);
  const tabs = tabsOf(table, row).filter((screen: Screen) => scopes === null || opens(scopes, screen.key));
  if (tabs.length < 2) return null;
  const prefix = agent === "" ? "" : `/a/${encodeURIComponent(agent)}`;

  return (
    <nav className="tabs" aria-label={`${row.name}'s screens`}>
      {tabs.map((screen) => (
        <NavLink key={screen.key} to={`${prefix}/${screen.path}`} end={screen.path === ""} className={({ isActive }) => (isActive || at.key === screen.key ? "tabs-tab tabs-tab-on" : "tabs-tab")}>
          {tabName(screen)}
        </NavLink>
      ))}
    </nav>
  );
}

/** What a row with no screen of its own draws: the way to the first of its tabs this key opens. */
export function FirstTab(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const scopes = useScopes();
  const { pathname } = useLocation();
  const table = agent === "" ? ORG_SCREENS : AGENT_SCREENS;
  const at = screenAt(pathname);
  // Nothing to land on before the key has said what it opens; once it has, a row none of whose
  // tabs open is not a row the sidebar drew, so this is a path typed by hand.
  if (at === undefined || scopes === null) return null;
  const first = tabsOf(table, at).find((screen) => opens(scopes, screen.key));
  if (first === undefined) return <Navigate to="/" replace />;
  return <Navigate to={`${agent === "" ? "" : `/a/${encodeURIComponent(agent)}`}/${first.path}`} replace />;
}
