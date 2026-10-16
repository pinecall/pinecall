/** Monitors, a tab of Quality: the numbers the world watches, the line each must not cross, and when each last did — every agent's, or the one in view's. */

import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Empty, Page, PageHead, Pill, Refused, TableHead, TableRow, TextAction } from "../../ui";
import { dropMonitor, type Monitor } from "./door";
import { ruleOf, valueOf } from "./metrics";
import { nameOf, useNames } from "../../lib/names";
import { NewMonitor } from "./new-monitor";
import { useMonitors } from "./use-monitors";
import "./monitors.css";

const COLUMNS = "minmax(0,1.2fr) minmax(0,1.6fr) 120px 100px 170px 56px";

/**
 * A monitor reads one number of the Observability series over 1, 7 or 30 days and fires — once a
 * day, as `monitor.fired` on the agent's log — the first time a call's seal finds it on the wrong
 * side of the line. The list is the world's; with one agent in view, that agent's and the ones
 * that watch every agent.
 */
export function Monitors(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const credentials = useCredentials();
  const { monitors, asking, setMonitors } = useMonitors();
  const names = useNames();
  const [writing, setWriting] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const shown = (monitors ?? []).filter((one) => agent === "" || one.agent === null || one.agent === agent);
  const fired = shown.filter((one) => one.fired_on !== null).length;
  const observability = agent === "" ? "/observability" : `/a/${encodeURIComponent(agent)}/observability`;

  const dropped = async (id: string): Promise<void> => {
    setRefused(null);
    try {
      await dropMonitor(credentials, id);
      setMonitors((monitors ?? []).filter((one) => one.id !== id));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <Page tight>
      <PageHead
        title="Monitors"
        lede={
          <>
            Lines the <Link to={observability}>numbers</Link> must not cross; one that does fires once a day.
          </>
        }
        actions={
          <Button kind="primary" size="sm" onClick={() => setWriting(true)} disabled={writing}>
            New monitor
          </Button>
        }
      />
      {writing && (
        <Card pad>
          <NewMonitor
            agent={agent}
            onSaved={(kept) => {
              setMonitors([...(monitors ?? []), kept]);
              setWriting(false);
            }}
            onClose={() => setWriting(false)}
          />
        </Card>
      )}
      <Card>
        <CardHead title="Watched" meta={monitors === null ? "reading…" : `${shown.length} monitor${shown.length === 1 ? "" : "s"} · ${fired} fired`} />
        <Refused>{asking ?? refused}</Refused>
        {monitors !== null && shown.length === 0 && !writing && (
          <Empty>
            Nothing is watched yet. A monitor is one number and a line: end-to-end latency above 2 s over 7 days, the judges' held rate below 90%, more than $20 a day. Set one here or with <code>pinecall monitors add</code>.
          </Empty>
        )}
        {shown.length > 0 && <TableHead columns={COLUMNS} labels={["Monitor", "Watches", "Agent", "Set by", "Last fired", ""]} />}
        {shown.map((one) => (
          <Row key={one.id} monitor={one} agent={agent} setBy={nameOf(names, one.created_by)} onDrop={() => void dropped(one.id)} />
        ))}
      </Card>
    </Page>
  );
}

function Row({ monitor, agent, setBy, onDrop }: { monitor: Monitor; agent: string; setBy: string; onDrop: () => void }): ReactNode {
  return (
    <TableRow columns={COLUMNS}>
      <span className="mon-name ui-clip" title={monitor.id}>
        {monitor.name}
      </span>
      <span className="mon-rule">{ruleOf(monitor)}</span>
      <span className={monitor.agent === null ? "ui-cell-faint" : "ui-cell-ink ui-clip"}>{monitor.agent ?? "every agent"}</span>
      <span className="ui-cell-faint ui-clip" title={monitor.created_by}>
        {setBy}
      </span>
      <span className="mon-fired">
        {monitor.fired_on === null ? (
          <span className="ui-cell-faint">never</span>
        ) : (
          <>
            <Pill tone="red" small>
              fired
            </Pill>
            <span className="ui-cell-ink">
              {monitor.fired_on} · {monitor.fired_value === null ? "" : valueOf(monitor.metric, monitor.fired_value)}
            </span>
          </>
        )}
      </span>
      <span className="mon-drop">
        {(agent === "" || monitor.agent === agent) && (
          <TextAction danger onClick={onDrop}>
            Drop
          </TextAction>
        )}
      </span>
    </TableRow>
  );
}
