/** An app's logs, streamed only while somebody has them open: the stream is what keeps the runner sending. */

import { useEffect, useState, type ReactNode } from "react";

import { doorUrl, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { openSse } from "@pinecall/core/stream";
import { ago } from "../lib/format";
import { logsIn, logsPath, type Logs } from "./door";

function Lines({ name }: { name: string }): ReactNode {
  const credentials = useCredentials();
  const [logs, setLogs] = useState<Logs | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(
    () =>
      openSse(doorUrl(credentials, logsPath(name)), credentials, {
        onMessage(message) {
          try {
            setLogs(logsIn(message.data));
            setRefused(null);
          } catch (failed) {
            setRefused(saidBy(failed));
          }
        },
        onConnection: () => undefined,
        onRefusedStream: setRefused,
      }),
    [credentials, name],
  );

  if (refused !== null) return <p className="app-refused">{refused}</p>;
  if (logs === null || (logs.lines === "" && logs.at === null)) return <p className="dash-quiet">Asking the box for its lines…</p>;
  return (
    <>
      <p className="dash-quiet app-logs-from">{[logs.host, logs.at === null ? null : `read ${ago(logs.at)}`].filter((part) => part !== null).join(", ")}</p>
      <pre className="app-logs">{logs.lines === "" ? "(no lines)" : logs.lines}</pre>
    </>
  );
}

export function LogsCard({ name }: { name: string }): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <section className="dash-card" aria-label="Logs">
      <div className="dash-card-top app-card-top-tight">
        <span className="dash-eyebrow">Logs</span>
        <button type="button" className="app-button" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Show"}
        </button>
      </div>
      {open && <Lines key={name} name={name} />}
    </section>
  );
}
