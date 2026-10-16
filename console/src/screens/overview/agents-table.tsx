/** Every agent of the org in one table, over the window the Overview reads: on the line, calls, how its judges held, its goldens. A row puts that agent in view. */

import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { type SessionLine } from "@pinecall/core/wire/rest";
import type { ReactNode } from "react";

import { percent } from "../../lib/format";
import type { Insights } from "../../lib/insights";
import { Avatar, Bar, Card, CardAction, CardHead, Pill, TableHead, TableRow } from "../../ui";
import type { Suite } from "../evals";

const COLUMNS = "minmax(0,1.6fr) 110px 80px minmax(0,1fr) 100px";

export function AgentsTable({
  agents,
  live,
  counted,
  suites,
  said,
}: {
  agents: readonly HeldAgent[];
  live: readonly SessionLine[];
  counted: Insights | null;
  suites: ReadonlyMap<string, Suite>;
  /** The window, as a sentence says it: "today", "the last 7 days". */
  said: string;
}): ReactNode {
  // An agent that took calls this window but is held by nobody now still has its row: its calls happened.
  const slugs = [...new Set([...agents.map((one) => one.slug), ...(counted?.agents ?? []).map((one) => one.slug)])].sort();
  if (slugs.length === 0) return null;
  return (
    <Card>
      <CardHead title="Agents" meta={`calls ${said} · a row puts that agent in view`} action={<CardAction to="/agents">Every agent</CardAction>} />
      <TableHead columns={COLUMNS} labels={["Agent", "On the line", "Calls>", "Held by the judges", "Goldens>"]} />
      {slugs.map((slug) => {
        const held = agents.find((one) => one.slug === slug);
        const calls = counted?.agents.find((one) => one.slug === slug);
        const onAir = live.filter((line) => line.agent === slug).length;
        const suite = suites.get(slug);
        return (
          <TableRow key={slug} columns={COLUMNS} to={`/a/${encodeURIComponent(slug)}/overview`}>
            <span className="ovw-agent">
              <Avatar size={26} name={slug} letters={slug.slice(0, 1).toUpperCase()} />
              <span className="ovw-agent-words">
                <span className="ui-cell-strong ui-clip">{slug}</span>
                <span className="ui-cell-faint ui-clip">{held === undefined ? "not held right now" : held.channels.join(" · ") || "no doors"}</span>
              </span>
            </span>
            <span>{onAir > 0 ? <Pill tone="green" small>{onAir} live</Pill> : <span className="ui-cell-faint">quiet</span>}</span>
            <span className="ui-cell-ink ui-cell-right ovw-num">{calls?.calls ?? 0}</span>
            <span className="ovw-held">
              {calls?.score == null ? (
                <span className="ui-cell-faint">nothing judged</span>
              ) : (
                <>
                  <Bar share={calls.score} />
                  <span className="ui-cell-ink ovw-num">{percent(calls.score)}</span>
                </>
              )}
            </span>
            <span className="ui-cell-right">
              {suite === undefined ? (
                <span className="ui-cell-faint">no run</span>
              ) : (
                <Pill tone={suite.held === suite.cells ? "green" : "red"} small>
                  {suite.held}/{suite.cells}
                </Pill>
              )}
            </span>
          </TableRow>
        );
      })}
    </Card>
  );
}
