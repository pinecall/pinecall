/** Overview's Processes card: connected app sockets, each with a stop button. */

import { type AppProcess, type HeldAgent } from "@pinecall/core/wire/rest-org";
import { useEffect, useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../../lib/format";
import { Card, CardHead, Refused, Item, TextAction } from "../../ui";
import { readProcesses, stopProcess } from "./door";

/**
 * One row per app socket. Re-read when `held` changes (a socket connected or left). Stop requires
 * the `app` scope.
 */
export function Processes({ held, stops }: { held: HeldAgent[]; stops: boolean }): ReactNode {
  const credentials = useCredentials();
  const [apps, setApps] = useState<AppProcess[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readProcesses(credentials).then(
      (read) => {
        if (!gone) setApps(read);
      },
      (failed: unknown) => {
        if (!gone) setRefused(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, held]);

  const stop = async (app: string): Promise<void> => {
    setRefused(null);
    try {
      await stopProcess(credentials, app);
      setApps(await readProcesses(credentials));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    }
  };

  if (apps === null && refused === null) return null;
  return (
    <Card>
      <CardHead title="Processes" meta="the machines holding these agents — a stop closes one, and it exits instead of dialling back" />
      <Refused>{refused}</Refused>
      <div className="ui-card-list">
        {apps?.length === 0 && <div className="agents-none">No process is connected.</div>}
        {apps?.map((app) => <Row key={app.app} app={app} stop={stops ? stop : undefined} />)}
      </div>
    </Card>
  );
}

function Row({ app, stop }: { app: AppProcess; stop: ((app: string) => Promise<void>) | undefined }): ReactNode {
  const [sure, setSure] = useState(false);
  const whose = app.holder === null ? "the org's" : (app.holder.name ?? app.holder.holder ?? "");
  const where = `${app.host ?? "an unnamed host"}${app.address === null ? "" : ` (${app.address})`}`;
  return (
    <div onMouseLeave={() => setSure(false)}>
      <Item
        name={app.agents.join(", ") || app.app}
        sub={`${where} · ${app.sdk ?? "an unknown sdk"} · ${whose} · connected ${ago(app.connected_at)}`}
        end={
          stop !== undefined && (
            <TextAction danger onClick={() => (sure ? void stop(app.app) : setSure(true))}>
              {sure ? "Stop it" : "Stop"}
            </TextAction>
          )
        }
      />
    </div>
  );
}
