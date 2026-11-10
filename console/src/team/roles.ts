/** The five roles in words: each one's name, who it is for and the doors its keys open, as rows a Select draws. */

import type { SelectItem } from "../ui/select";
import type { Person, Role } from "./door";

// A role is a preset of scopes for the keys a person mints; the doors check scopes, never the role.
export const ROLE_OPENS: Record<Role, { name: string; who: string; opens: string }> = {
  qa: { name: "QA", who: "Reads finished calls and the suites", opens: "calls · evals" },
  supervisor: { name: "Supervisor", who: "Sits beside a live call: listens, whispers, takes it over", opens: "calls · evals · supervise · talk · memory · words" },
  manager: { name: "Manager", who: "Runs the floor and the org's accounts, never the agent's declaration", opens: "calls · evals · supervise · talk · memory · numbers · keys · providers · usage · team · words" },
  developer: { name: "Developer", who: "Writes and runs the agent", opens: "app · calls · talk · supervise · pipeline · knowledge · memory · evals · words" },
  admin: { name: "Admin", who: "The org's owner", opens: "every door" },
};

const ORDER: readonly Role[] = ["qa", "supervisor", "manager", "developer", "admin"];

export const ROLE_ITEMS: readonly SelectItem[] = ORDER.map((role) => ({ value: role, label: ROLE_OPENS[role].name, detail: ROLE_OPENS[role].who, keywords: ROLE_OPENS[role].opens }));

/** How a person stands, in the word and the colour of a row's status. */
export const STANDS: Record<Person["status"], { word: string; mood: "held" | "waiting" | "none" }> = {
  active: { word: "Active", mood: "held" },
  invited: { word: "Invited", mood: "waiting" },
  disabled: { word: "Disabled", mood: "none" },
};
