/** Overview: who is on the line, the window's numbers, calls a day beside how calls end, and what needs a look — every agent's, or the one in view. */

import { useMemo, type ReactNode } from "react";
import { Navigate, useParams } from "react-router";

import { seconds } from "@pinecall/core/metrics";
import { change, percent, spend, utcDay } from "../../lib/format";
import { useInsights, useWindowDays, WindowPicker, windowSaid, type Insights } from "../../lib/insights";
import { useLimits } from "../../lib/limits";
import { useOrg } from "../../lib/org";
import { useWhoami } from "../../lib/whoami";
import { Card, CardHead, Empty, Page, PageHead, Stat, Stats } from "../../ui";
import { useSuites } from "../evals";
import { AgentsTable } from "./agents-table";
import { CallsByDay, CHANNEL_NAME, Legend, Shares } from "./charts";
import { CHANNELS, daysOf, windowWithCalls } from "./counted";
import { LimitsCard } from "./limits-card";
import { NeedsALook } from "./needs-a-look";
import { OnTheLine } from "./on-the-line";
import { isFirstRun } from "../welcome/first-run";
import { Setup } from "./setup";
import { Speed } from "./speed";
import "./overview.css";

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 19 ? "Good afternoon" : "Good evening";
}

/**
 * One screen for both: with every agent in view it is the org's morning — the greeting, the agents
 * side by side, what is left to set up — and with one in view it is that agent's, with how fast it
 * answers. The numbers are the gateway's count over the window picked (`?days=`), however many
 * calls it holds; unpicked, the window is the shortest that holds a call, read off the last 30 days.
 */
export function Overview(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const whose = useWhoami();
  const { lines, live, agents, agentsLoaded } = useOrg();
  const asked = agent === "" ? undefined : agent;
  const month = useInsights({ agent: asked, days: 30 });
  const busiest = month === null ? undefined : windowWithCalls(daysOf(month.series));
  const [range, pickRange, picked] = useWindowDays(busiest ?? 1);
  const answered = useInsights({ agent: asked, days: range });
  const before = useInsights({ agent: asked, day: utcDay(Date.now() / 1000 - range * 86400), days: range });
  // Nothing is drawn until the window is known, nor a count of another window than the one shown.
  const counted = (picked || busiest !== undefined) && answered?.days === range ? answered : null;
  const days = useMemo(() => daysOf(counted?.series ?? []), [counted]);
  const suites = useSuites();
  const limits = useLimits();

  const mine = agent === "" ? lines : lines.filter((line) => line.agent === agent);
  const onAir = agent === "" ? live : live.filter((line) => line.agent === agent);
  const theirSuites = [...suites.values()].filter((suite) => agent === "" || suite.agent === agent);
  const first = (whose?.name ?? "").split(" ")[0] ?? "";
  const said = windowSaid(range);

  // A new org opens on the guide, once; the browser remembers it was shown or skipped.
  if (agent === "" && isFirstRun(agentsLoaded, agents.length)) return <Navigate to="/welcome" replace />;

  return (
    <Page>
      <div className="ovw">
        <PageHead
          title={agent !== "" ? agent : first === "" ? greeting() : `${greeting()}, ${first}`}
          lede={standing(onAir.length, onAir.some((line) => line.attention?.status === "open"), agent)}
          actions={<WindowPicker days={range} onPick={pickRange} />}
        />

        {agent === "" && <Setup agents={agents.length} limits={limits} />}

        <section className="ovw-section" aria-label="On the line now">
          <div className="ovw-section-head">
            <span className={onAir.length > 0 ? "ovw-pulse ovw-pulse-on" : "ovw-pulse"} aria-hidden />
            On the line now
          </div>
          <OnTheLine live={onAir} agent={agent} />
        </section>

        <Stats min={170} apart>
          <Numbers counted={counted} before={before} said={said} />
        </Stats>

        <div className="ovw-pair">
          <Card>
            <CardHead title="Calls a day" meta={<Legend />} />
            {counted === null ? <Empty>Counting the calls…</Empty> : <CallsByDay days={days} />}
          </Card>
          <div className="ovw-column">
            <Card>
              <CardHead title="How calls end" meta={said} />
              {(counted?.endings.length ?? 0) === 0 ? (
                <Empty>No call has ended {said}.</Empty>
              ) : (
                <Shares rows={(counted?.endings ?? []).slice(0, 6).map((one) => ({ name: one.reason.replace(/_/g, " "), count: one.count }))} />
              )}
              {agent === "" && (
                <div className="ovw-card-part">
                  <CardHead title="Where calls come in" meta={said} />
                  <Shares tone="channel" rows={CHANNELS.map((channel) => ({ name: CHANNEL_NAME[channel], count: counted?.channels[channel] ?? 0, key: channel }))} />
                </div>
              )}
            </Card>
            {agent !== "" && <Speed agent={agent} />}
          </div>
        </div>

        <NeedsALook lines={mine} suites={theirSuites} agent={agent} />

        {agent === "" && limits !== null && <LimitsCard limits={limits} />}

        {agent === "" && <AgentsTable agents={agents} live={live} counted={counted} suites={suites} said={said} />}
      </div>
    </Page>
  );
}

/** The sentence under the title: who is on the line, and whether one of them is waiting for a person. */
function standing(onAir: number, asking: boolean, agent: string): string {
  const who = agent === "" ? "" : ` with ${agent}`;
  if (onAir === 0) return `Nobody is on the line${who} right now.`;
  const calls = onAir === 1 ? `One call is on the line${who}` : `${onAir} calls are on the line${who}`;
  return asking ? `${calls}, and a caller is waiting for a person.` : `${calls}.`;
}

/** The window's five numbers, the first four against the window of the same length before it. */
function Numbers({ counted, before, said }: { counted: Insights | null; before: Insights | null; said: string }): ReactNode {
  if (counted === null) {
    return ["Calls", "Resolved without a person", "Held by the judges", "Median answer", "Spend"].map((label) => <Stat key={label} size="big" label={label} value="—" />);
  }
  const calls = counted.conversations.now;
  const moved = change(calls, counted.conversations.before);
  const resolved = counted.resolved_rate;
  const resolvedBefore = before?.resolved_rate ?? null;
  const points = resolved === null || resolvedBefore === null ? null : Math.round((resolved - resolvedBefore) * 100);
  const median = counted.median_e2e_s;
  const medianBefore = before?.median_e2e_s ?? null;
  const faster = median === null || medianBefore === null ? null : Math.round((median - medianBefore) * 10) / 10;
  const limit = counted.budget.limit_usd;
  return (
    <>
      <Stat size="big" label="Calls" value={calls} delta={moved?.text ?? said} tone={moved?.tone ?? "flat"} />
      <Stat
        size="big"
        label="Resolved without a person"
        value={resolved === null ? "—" : percent(resolved)}
        delta={points === null ? said : points === 0 ? "steady" : `${points > 0 ? "+" : "−"}${Math.abs(points)} pts`}
        tone={points === null || points === 0 ? "flat" : points > 0 ? "up" : "down"}
      />
      <Stat size="big" label="Held by the judges" value={counted.judged === 0 ? "—" : percent(counted.passed / counted.judged)} delta={counted.judged === 0 ? "nothing judged" : `${counted.passed} of ${counted.judged}`} tone="flat" />
      <Stat
        size="big"
        label="Median answer"
        value={median === null ? "—" : seconds(median)}
        delta={faster === null ? said : Math.abs(faster) < 0.1 ? "steady" : `${faster > 0 ? "+" : "−"}${Math.abs(faster).toFixed(1)}s`}
        tone={faster === null || Math.abs(faster) < 0.1 ? "flat" : faster > 0 ? "down" : "up"}
      />
      <Stat size="big" label="Spend" value={spend(counted.spend_usd)} delta={limit === null ? said : `of $${limit} a month`} tone="flat" />
    </>
  );
}
