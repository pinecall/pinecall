/** The org's alerts kept, newest first: what it was told, whether a webhook was set or not. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../../lib/format";
import { Card, CardHead, Empty, KV, Pill, Refused } from "../../ui";
import { readAlerts, type Alert } from "./door";

/** The kinds in plain words, as the screen's own list names them. */
const NAMED: Record<string, string> = {
  "monitor.fired": "A monitor fired",
  "spend.unusual": "Unusual spend",
  "credits.exhausted": "Out of quota",
  "app.failed": "An app went down",
};

/** What one alert is about: the monitor's name, the app, the quota; the org's spend has none. */
function about(one: Alert): string {
  const named = one.data["name"] ?? one.data["app"] ?? one.data["quota"];
  return typeof named === "string" ? named : "";
}

export function Recent(): ReactNode {
  const credentials = useCredentials();
  const [alerts, setAlerts] = useState<Alert[] | undefined>(undefined);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readAlerts(credentials).then(
      (found) => {
        if (!gone) setAlerts(found);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  return (
    <Card>
      <CardHead title="Recent alerts" meta="kept for 90 days, mailed to the org's admins, whether or not a webhook is connected" />
      {alerts !== undefined && alerts.length === 0 && <Empty>Nothing needed attention here yet.</Empty>}
      {alerts !== undefined && alerts.length > 0 && (
        <div className="alr-rows">
          {alerts.map((one) => (
            <KV key={one.id} keyWidth={150} label={ago(Date.parse(one.at) / 1000)}>
              {NAMED[one.kind] ?? one.kind}
              {about(one) === "" ? "" : ` · ${about(one)}`}
              {one.agent === null ? "" : ` · ${one.agent}`}{" "}
              <Pill tone={one.mailed ? "green" : "gray"} small>
                {one.mailed ? "Mailed" : "Not mailed"}
              </Pill>
            </KV>
          ))}
        </div>
      )}
      <Refused>{refused}</Refused>
    </Card>
  );
}
