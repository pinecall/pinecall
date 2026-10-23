/** An agent's cases as one line each — the name, who kept or wrote it and when — opening on the Cases screen, with room under each for what a screen adds. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { ago } from "../../lib/format";
import { ownedAt } from "../../lib/harness";
import type { EvalCase } from "./door";

export function CaseList({
  agent,
  cases,
  under,
}: {
  /** The agent in view, or "" for every agent: where a case opens. */
  agent: string;
  cases: readonly EvalCase[];
  /** What a screen says under a case's line: a run's verdict, why it is not played. */
  under?: ((kept: EvalCase) => ReactNode) | undefined;
}): ReactNode {
  return (
    <ul className="cs-by-hand">
      {cases.map((kept) => (
        <li key={kept.id}>
          <Link to={ownedAt(agent, "cases", kept.agent, kept.name)}>
            <span className="cs-g-said-line">{kept.name}</span>
            <span className="cs-g-from">
              {kept.source === "person" ? "written" : "kept from a call"} by {kept.author} · {ago(kept.created_at)}
              {kept.held_out && " · held out"}
            </span>
          </Link>
          {under?.(kept)}
        </li>
      ))}
    </ul>
  );
}
