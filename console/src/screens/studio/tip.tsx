/** What the judges found wrong in this agent's calls, said once above its instructions, with the way to the cases it came from. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { Icon } from "../../ui";
import { useCases } from "../cases";

export function Tip({ agent }: { agent: string }): ReactNode {
  const { groups } = useCases(agent);
  const found = (groups ?? []).find((group) => group.status === "pending");
  if (found === undefined) return null;
  return (
    <div className="sto-tip">
      <span className="sto-tip-icon" aria-hidden>
        <Icon name="bulb" size={17} />
      </span>
      <span className="sto-tip-said">
        Judges flagged {found.cases} {found.cases === 1 ? "call" : "calls"}: {found.cause}
      </span>
      <Link to={`/a/${encodeURIComponent(agent)}/cases`} className="sto-tip-go">
        See them in Cases
      </Link>
    </div>
  );
}
