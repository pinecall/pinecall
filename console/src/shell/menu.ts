/** The one menu: the same rows whichever agent, world or page; an agent is a page you open, never a mode of the menu. */

import { WORLD } from "../lib/world";
import type { IconName } from "./icons";

export interface Row {
  path: string;
  name: string;
  icon: IconName;
}

export interface Group {
  title: string | null;
  rows: readonly Row[];
}

export const MENU: readonly Group[] = [
  { title: "Home", rows: [{ path: "/", name: "Dashboard", icon: "dashboard" }] },
  {
    title: "Build",
    rows: [
      { path: "/apps", name: "Apps", icon: "apps" },
      { path: "/agents", name: "Agents", icon: "agents" },
      { path: "/knowledge", name: "Knowledge", icon: "knowledge" },
      { path: "/numbers", name: "Numbers", icon: "numbers" },
    ],
  },
  {
    title: "Observe",
    rows: [
      { path: "/calls", name: "Calls", icon: "calls" },
      { path: "/quality", name: "Quality", icon: "quality" },
      { path: "/observability", name: "Observability", icon: "observability" },
      { path: "/monitors", name: "Monitors", icon: "monitors" },
    ],
  },
  {
    title: "Harness",
    rows: [
      { path: "/goldens", name: "Goldens", icon: "goldens" },
      // Production places one call of one caller: the row is named for that.
      { path: "/simulations", name: WORLD === "production" ? "Check call" : "Simulations", icon: "simulations" },
      { path: "/personas", name: "Personas", icon: "personas" },
      { path: "/judges", name: "Judges", icon: "judges" },
      { path: "/cases", name: "Cases", icon: "cases" },
    ],
  },
  {
    title: "Manage",
    rows: [
      { path: "/team", name: "Team", icon: "team" },
      { path: "/usage", name: "Usage", icon: "usage" },
      { path: "/billing", name: "Billing", icon: "billing" },
      { path: "/privacy", name: "Privacy", icon: "privacy" },
      { path: "/settings", name: "Settings", icon: "settings" },
    ],
  },
];

/** The box's own pages, in the menu only for those who run it. */
export const OPERATOR_MENU: Group = {
  title: "Box",
  rows: [
    { path: "/box/orgs", name: "Organizations", icon: "building" },
    { path: "/box/fleet", name: "Fleet", icon: "server" },
    { path: "/box/carriers", name: "Carriers", icon: "numbers" },
    { path: "/box/routes", name: "Routes", icon: "route" },
    { path: "/box/traceback", name: "Traceback", icon: "numbers" },
    { path: "/box/usage", name: "Box usage", icon: "usage" },
    { path: "/box/settings", name: "Box settings", icon: "settings" },
  ],
};

// Reached from the bell at the sidebar's foot, not from a row of the menu.
const NOTIFICATIONS: Row = { path: "/notifications", name: "Notifications", icon: "bell" };

/** The menu's row a page belongs to; `/agents/front-desk` is Agents'. */
export function rowOfPage(page: string): Row | undefined {
  const rows = [...MENU.flatMap((group) => group.rows), ...OPERATOR_MENU.rows, NOTIFICATIONS];
  return page === "/" ? rows[0] : rows.find((row) => row.path !== "/" && (page === row.path || page.startsWith(`${row.path}/`)));
}
