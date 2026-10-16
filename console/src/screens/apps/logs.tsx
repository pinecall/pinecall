/** An app's logs, as the platform sends them for as long as the panel is open: the stream is what keeps the runner sending. */

import { useEffect, useState, type ReactNode } from "react";

import { doorUrl, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { openSse } from "@pinecall/core/stream";
import { Card, CardHead, Refused, TextAction } from "../../ui";
import { logsIn, logsPath, type Logs } from "./door";
import { readAgo } from "./fold";

export function LogsPanel({ name, close }: { name: string; close: () => void }): ReactNode {
  const credentials = useCredentials();
  const [logs, setLogs] = useState<Logs | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);

  useEffect(() => {
    // The runner sends an app's lines with its beat; each time it does, the gateway sends them here.
    return openSse(doorUrl(credentials, logsPath(name)), credentials, {
      onMessage(message) {
        try {
          setLogs(logsIn(message.data));
          setRefused(null);
          setNow(Date.now() / 1000);
        } catch (failed) {
          setRefused(saidBy(failed));
        }
      },
      onConnection: () => undefined,
      onRefusedStream: setRefused,
    });
  }, [credentials, name]);

  const waiting = logs === null || (logs.lines === "" && logs.at === null);
  const meta = logs === null ? undefined : [readAgo(logs.at, now), logs.host].filter((part) => part !== null).join(" · ");

  return (
    <Card>
      <CardHead title={`Logs · ${name}`} meta={meta} action={<TextAction onClick={close}>Close</TextAction>} />
      <Refused>{refused}</Refused>
      {waiting ? <div className="apps-waiting">asking the box for its lines…</div> : <pre className="ui-code apps-lines">{logs.lines === "" ? "(no lines)" : logs.lines}</pre>}
    </Card>
  );
}
