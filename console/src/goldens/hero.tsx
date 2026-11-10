/** The Goldens page's headline: how many goldens the agents in view have, how their last runs went, and how many agents have none. */

import type { ReactNode } from "react";

import { count } from "../lib/format";
import type { Tally } from "./fold";
import { Standing } from "./group";

interface Figure {
  title: string;
  value: string;
  under: string;
  mood?: "good" | "warn" | "bad" | undefined;
}

export function Hero({ tally, agents, without, reading }: { tally: Tally; /** The agents in view. */ agents: number; /** Of those read, how many have no golden. */ without: number; /** How many are still being read. */ reading: number }): ReactNode {
  const goldens = tally.held + tally.broke + tally.none;
  const figures: Figure[] = [
    { title: "Held", value: count(tally.held), under: "In their last run", mood: tally.held > 0 ? "good" : undefined },
    { title: "Broke", value: count(tally.broke), under: "In their last run", mood: tally.broke > 0 ? "bad" : undefined },
    { title: "Not run", value: count(tally.none), under: "Never played here" },
    { title: "Agents with none", value: count(without), under: without === 0 ? "Every agent has one" : `Of ${agents}`, mood: without > 0 ? "warn" : undefined },
  ];
  return (
    <section className="dash-card gd-hero" aria-label="Goldens">
      <div className="gd-hero-main">
        <span className="dash-eyebrow">Goldens</span>
        <p className="gd-figure">{count(goldens)}</p>
        <p className="dash-quiet">
          {agents === 1 ? "On one agent." : `Across ${agents} agents.`}
          {reading > 0 && ` Still reading ${reading}.`}
        </p>
        {goldens > 0 && <Standing tally={tally} wide />}
      </div>
      <div className="gd-counts">
        {figures.map((figure) => (
          <div key={figure.title} className="dash-part gd-count">
            <span className="dash-eyebrow">{figure.title}</span>
            <span className={figure.mood === undefined ? "dash-part-value" : `dash-part-value dash-mood-${figure.mood}`}>{figure.value}</span>
            <span className="dash-quiet dash-clip">{figure.under}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
