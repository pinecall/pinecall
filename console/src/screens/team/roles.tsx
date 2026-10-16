/** Table of what each role can access, linked from the invite form. */

import type { ReactNode } from "react";

import { Card, CardHead, TableHead, TableRow } from "../../ui";
import type { Member } from "./door";

// A role is a scope preset (runtime auth/roles) for keys minted later. Doors check scopes, not roles.
export const ROLE_OPENS: Record<Member["role"], { who: string; opens: string }> = {
  qa: { who: "Reads finished calls and the suites", opens: "calls · evals" },
  supervisor: { who: "Sits beside a live call: listens, whispers, takes it over", opens: "calls · evals · supervise · talk · memory · words" },
  manager: { who: "Runs the floor and the org's accounts, never the agent's declaration", opens: "calls · evals · supervise · talk · memory · numbers · keys · providers · usage · team · words" },
  developer: { who: "Writes and runs the agent", opens: "app · calls · talk · supervise · pipeline · knowledge · memory · evals · words" },
  admin: { who: "The org's owner", opens: "every door" },
};

const ORDER: readonly Member["role"][] = ["qa", "supervisor", "manager", "developer", "admin"];
const COLUMNS = "110px minmax(0,1fr) minmax(0,1.4fr)";

export function Roles(): ReactNode {
  return (
    <Card>
      <CardHead title="Roles" meta="a preset of what a person's keys open — and where: the sandbox always, production when their switch is on (an admin's always is)" />
      <TableHead columns={COLUMNS} labels={["Role", "Who", "Opens"]} />
      {ORDER.map((role) => (
        <TableRow key={role} columns={COLUMNS}>
          <span className="ui-cell-strong">{role}</span>
          <span className="ui-cell-ink">{ROLE_OPENS[role].who}</span>
          <span className="ui-cell-faint team-role-opens">{ROLE_OPENS[role].opens}</span>
        </TableRow>
      ))}
    </Card>
  );
}
