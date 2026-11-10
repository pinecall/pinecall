/** The top of the dashboard: the agents and the apps and how they stand, who is on the line now, and the alerts of the week. */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import type { SessionLine } from "@pinecall/core/wire/rest";
import { Avatar } from "../apps/avatar";
import { appsOf, saidOf, type App } from "../apps/fold";
import { ago } from "../lib/format";
import { useOrg } from "../lib/org";
import { readAlerts, type Alert } from "../monitors/door";
import { alertOf } from "../monitors/words";
import { Icon, type IconName } from "../shell/icons";

const WEEK_S = 7 * 86400;
const FACES = 4;

/** When an alert was left, in seconds. */
export function leftAt(alert: Alert): number {
  return Date.parse(alert.at) / 1000;
}

/** The org's alerts, newest first; null until read, and for a key that may not read them. */
export function useAlerts(): Alert[] | null {
  const credentials = useCredentials();
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  useEffect(() => {
    let gone = false;
    readAlerts(credentials).then((said) => !gone && setAlerts(said), () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials]);
  return alerts;
}

/** Both lists of the org as the Agents and Apps pages draw them. */
export function useFleet(): { studio: App[]; code: App[] } {
  const { agents, hosted } = useOrg();
  return useMemo(() => ({ studio: appsOf(hosted ?? [], agents, "studio"), code: appsOf(hosted ?? [], agents, "code") }), [hosted, agents]);
}

/** How a list stands, in a line: `3 live, 1 failed, 1 stopped`. */
function standing(apps: readonly App[], none: string): { said: string; mood: "calm" | "bad" } {
  const moods = apps.map((one) => saidOf(one).mood);
  const of = (mood: string): number => moods.filter((one) => one === mood).length;
  const parts = [of("good") > 0 && `${of("good")} live`, of("warn") > 0 && `${of("warn")} on its way`, of("bad") > 0 && `${of("bad")} failed`, of("calm") > 0 && `${of("calm")} off`].filter((part) => part !== false);
  return { said: parts.length === 0 ? none : parts.join(", "), mood: of("bad") > 0 ? "bad" : "calm" };
}

function Card({ to, name, icon, value, under, mood, children }: { to: string; name: string; icon: IconName; value: string; under: string; mood: "calm" | "good" | "warn" | "bad"; children?: ReactNode }): ReactNode {
  return (
    <Link to={to} className="dash-card dash-station">
      <span className="dash-eyebrow">
        <Icon name={icon} size={14} />
        {name}
      </span>
      <span className="dash-station-line">
        <span className={`dash-big dash-mood-${mood}`}>{value}</span>
        {children}
      </span>
      <span className="dash-quiet dash-clip">{under}</span>
    </Link>
  );
}

function Faces({ apps, kind }: { apps: readonly App[]; kind: "code" | "studio" }): ReactNode {
  if (apps.length === 0) return null;
  return (
    <span className="dash-faces" aria-hidden="true">
      {apps.slice(0, FACES).map((one) => (
        <Avatar key={one.name} kind={kind} name={one.name} size={26} />
      ))}
      {apps.length > FACES && <span className="dash-faces-more">+{apps.length - FACES}</span>}
    </span>
  );
}

export function FleetCards({ live, alerts }: { live: readonly SessionLine[]; alerts: readonly Alert[] | null }): ReactNode {
  const { studio, code } = useFleet();
  const agents = standing(studio, "Built in Studio, none yet");
  const apps = standing(code, "Written as code, none yet");
  const by = (channel: string): number => live.filter((line) => line.channel === channel).length;
  const onLine = [by("phone") > 0 && `${by("phone")} phone`, by("web") > 0 && `${by("web")} web`, by("whatsapp") > 0 && `${by("whatsapp")} WhatsApp`].filter((part) => part !== false);
  const week = (alerts ?? []).filter((one) => leftAt(one) > Date.now() / 1000 - WEEK_S);
  const newest = alerts?.[0];
  return (
    <div className="dash-fleet">
      <Card to="/agents" name="Agents" icon="agents" value={String(studio.length)} under={agents.said} mood={agents.mood}>
        <Faces apps={studio} kind="studio" />
      </Card>
      <Card to="/apps" name="Apps" icon="apps" value={String(code.length)} under={apps.said} mood={apps.mood}>
        <Faces apps={code} kind="code" />
      </Card>
      <Card to="/calls" name="Live now" icon="wave" value={String(live.length)} under={live.length === 0 ? "Nobody on the line" : onLine.length === 0 ? "On the line now" : onLine.join(", ")} mood={live.length > 0 ? "good" : "calm"} />
      <Card to="/monitors" name="Alerts" icon="bell" value={alerts === null ? "—" : String(week.length)} under={newest === undefined ? "Nothing has needed attention" : week.length === 0 ? `None in 7 days, the last ${ago(leftAt(newest))}` : `In 7 days. ${alertOf(newest).title}, ${ago(leftAt(newest))}`} mood={week.length > 0 ? "warn" : "calm"} />
    </div>
  );
}
