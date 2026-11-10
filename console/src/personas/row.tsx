/** One persona in the list: its name, a dot for how its newest call went, and whose it is or what it is after under them. */

import type { ReactNode } from "react";
import { Link, type To } from "react-router";

import { PersonaAvatar } from "../apps/avatar";
import { standingOf, type Persona, type PersonaRun, type Standing } from "../simulations/door";
import { goalOf, saidOf } from "./fold";

export const DOTS: Record<Standing, string> = { live: "app-dot app-dot-warn", held: "app-dot app-dot-good", broke: "app-dot app-dot-bad", unjudged: "app-dot app-dot-calm" };

export function Row({ persona, whose, last, open, to }: { persona: Persona; whose: string | undefined; last: PersonaRun | undefined; open: boolean; to: To }): ReactNode {
  return (
    <Link to={to} aria-current={open ? "true" : undefined} className={open ? "app-row app-row-on ps-item" : "app-row ps-item"}>
      <PersonaAvatar name={persona.name} size={30} />
      <span className="ps-item-words">
        <span className="app-row-top">
          <span className="dash-clip">{persona.name}</span>
          {last !== undefined && <span className={DOTS[standingOf(last)]} title={saidOf(last)} aria-hidden="true" />}
        </span>
        <span className="app-row-under dash-clip">{whose ?? goalOf(persona)}</span>
      </span>
    </Link>
  );
}
