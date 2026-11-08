/** The harness on the dashboard: the six stations an agent goes through, each with its number now and what it is for. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { percent } from "../lib/format";
import type { Harness } from "../lib/harness";
import { Icon, type IconName } from "../shell/icons";

type Mood = "calm" | "good" | "warn" | "bad";

interface Station {
  to: string;
  name: string;
  icon: IconName;
  does: string;
  value: string;
  under: string;
  mood: Mood;
}

function stationsOf(harness: Harness, judged: number, passed: number, days: number): Station[] {
  const { personas, simulations, goldens, cases, monitors } = harness;
  const goldenCount = goldens === null ? 0 : goldens.passing + goldens.failing;
  return [
    { to: "/personas", name: "Personas", icon: "personas", does: "The callers written for your agents: a goal, a manner, the facts they know.", value: personas === null ? "—" : String(personas), under: "Switched on", mood: "calm" },
    { to: "/simulations", name: "Simulations", icon: "simulations", does: "A persona on the line, written or out loud, judged when it hangs up.", value: simulations === null ? "—" : String(simulations), under: "Calls played", mood: "calm" },
    { to: "/judges", name: "Judges", icon: "judges", does: "The questions every call is held to when it ends.", value: judged === 0 ? "—" : percent(passed / judged), under: judged === 0 ? `Nothing judged in ${days} days` : `Held, of ${judged} in ${days} days`, mood: judged === 0 ? "calm" : passed / judged >= 0.9 ? "good" : "warn" },
    { to: "/goldens", name: "Goldens", icon: "goldens", does: "Conversations written down and replayed before a change ships.", value: goldens === null || goldenCount === 0 ? "—" : `${goldens.passing}/${goldenCount}`, under: goldenCount === 0 ? "Not run yet" : "Held in the last run", mood: goldenCount === 0 ? "calm" : (goldens?.failing ?? 0) > 0 ? "bad" : "good" },
    { to: "/cases", name: "Cases", icon: "cases", does: "Real calls a judge broke on, kept whole until somebody decides.", value: cases === null ? "—" : String(cases), under: "Waiting for a person", mood: (cases ?? 0) > 0 ? "warn" : "calm" },
    { to: "/monitors", name: "Monitors", icon: "monitors", does: "The numbers watched over days, and the line each must not cross.", value: monitors === null ? "—" : String(monitors.watching), under: monitors === null || monitors.fired === 0 ? "None fired" : `${monitors.fired} fired`, mood: (monitors?.fired ?? 0) > 0 ? "bad" : "calm" },
  ];
}

export function HarnessCards({ harness, judged, passed, days }: { harness: Harness; judged: number; passed: number; days: number }): ReactNode {
  return (
    <div className="dash-stations">
      {stationsOf(harness, judged, passed, days).map((station) => (
        <Link key={station.to} to={station.to} className="dash-card dash-station" title={station.does}>
          <span className="dash-eyebrow">
            <Icon name={station.icon} size={14} />
            {station.name}
          </span>
          <span className={`dash-big dash-mood-${station.mood}`}>{station.value}</span>
          <span className="dash-quiet">{station.under}</span>
        </Link>
      ))}
    </div>
  );
}
