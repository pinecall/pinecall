/** Quality's overview: how the REAL calls are going — judged at hang-up — for every agent or the one in view: the share that held, a day at a time, what broke, and by agent. */

import { useMemo, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { whoOn } from "@pinecall/core/calls";
import { ago, percent, webVisitor } from "../../lib/format";
import { useInsights } from "../../lib/insights";
import { useOrg } from "../../lib/org";
import { Bar, Card, CardHead, Page, PageHead, Stat, Stats, TableHead, TableRow } from "../../ui";
import { HeldByDay } from "./held-by-day";
import "./quality.css";

// The numbers across are a week's; the line is a month's, so a week reads against what came before.
const WEEK = 7;
const MONTH = 30;
// What broke is read off the calls the page already follows: the newest, not all of them.
const BROKE_SHOWN = 8;
const AGENT_COLUMNS = "minmax(0,1.4fr) 90px minmax(0,1fr)";

/**
 * Quality is about calls that happened; whether a change is safe before it ships is Test's. The
 * week's numbers and the line are the gateway's count (`/v1/insights`); what broke is the calls
 * the page follows whose judges said no, each with the judge's own reason; the judges' held-rates
 * are Test's Judges tab's, and the lines its numbers must not cross are the Monitors tab's.
 */
export function Quality(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const { lines } = useOrg();
  const asked = agent === "" ? undefined : agent;
  const week = useInsights({ agent: asked, days: WEEK });
  const month = useInsights({ agent: asked, days: MONTH });
  const mine = useMemo(() => (agent === "" ? lines : lines.filter((line) => line.agent === agent)), [lines, agent]);
  const broke = mine.filter((line) => line.score?.passed === false).slice(0, BROKE_SHOWN);
  const calls = agent === "" ? "/calls" : `/a/${encodeURIComponent(agent)}/calls`;
  const judged = week?.judged ?? 0;

  return (
    <Page>
      <PageHead
        title="Quality"
        lede="Real calls, judged at hang-up."
      />

      <Stats min={170}>
        <Stat size="big" label="Calls judged" value={week === null ? "—" : judged} delta="the last 7 days" tone="flat" />
        <Stat size="big" label="Held" value={week === null || judged === 0 ? "—" : percent(week.passed / judged)} delta={judged === 0 ? "nothing judged" : `${week?.passed ?? 0} of ${judged}`} tone="flat" />
        <Stat size="big" label="Broke" value={week === null ? "—" : judged - (week.passed ?? 0)} delta={<Link to={`${calls}?status=broke`}>See them in Calls</Link>} tone="flat" />
      </Stats>

      <div className="qly-split">
        <Card>
          <CardHead title="Held, a day at a time" meta="share of judged calls where every judge held · the last 30 days" />
          {month === null ? <p className="qly-quiet">Counting the verdicts…</p> : <HeldByDay series={month.series} />}
        </Card>
        <Card>
          <CardHead title="What broke" meta="the judge's own reason" />
          {broke.length === 0 ? (
            <p className="qly-quiet">Every judged call the page follows held.</p>
          ) : (
            <div className="qly-broke">
              {broke.map((line) => (
                <Link key={line.call} to={`${calls}/${line.call}`} className="qly-broke-one">
                  <span className="qly-broke-mark" aria-hidden />
                  <span className="qly-broke-words">
                    <span className="qly-broke-who">
                      {whoOn(line, webVisitor)}
                      {agent === "" && <span className="qly-broke-agent"> · {line.agent}</span>}
                    </span>
                    <span className="qly-broke-why">{line.score?.reason ?? "A judge answered broken."}</span>
                  </span>
                  <span className="qly-broke-when">
                    {line.score?.held}/{line.score?.judged} · {ago(line.started_at)}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>

      {agent === "" && (week?.agents.length ?? 0) > 0 && (
        <Card>
          <CardHead title="By agent" meta="the last 7 days · a row puts that agent in view" />
          <TableHead columns={AGENT_COLUMNS} labels={["Agent", "Calls>", "Held by the judges"]} />
          {(week?.agents ?? []).map((one) => (
            <TableRow key={one.slug} columns={AGENT_COLUMNS} to={`/a/${encodeURIComponent(one.slug)}/quality`}>
              <span className="ui-cell-strong ui-clip">{one.slug}</span>
              <span className="ui-cell-ink ui-cell-right qly-num">{one.calls}</span>
              <span className="qly-held">
                {one.score === null ? (
                  <span className="ui-cell-faint">nothing judged</span>
                ) : (
                  <>
                    <Bar share={one.score} />
                    <span className="ui-cell-ink qly-num">{percent(one.score)}</span>
                  </>
                )}
              </span>
            </TableRow>
          ))}
        </Card>
      )}
    </Page>
  );
}
