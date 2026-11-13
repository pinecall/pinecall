/** An app or a Studio agent's overview: what its calls say; an app's measures too, and a Studio agent's releases. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { seconds } from "@pinecall/core/metrics";
import { readReport, type Report } from "../configure/door";
import { Ring } from "../configure/measures";
import { MeasuresCard, measuringOf } from "../configure/measures-card";
import { DayChart, type Point } from "../dashboard/charts";
import { Part } from "../dashboard/overview";
import { count, dayLabel, money, percent } from "../lib/format";
import { callsOf, useInsights } from "../lib/insights";
import { WORLD } from "../lib/world";
import { whoIs } from "./door";
import { Avatar } from "./avatar";
import { hours, isOfAgents, saidOf, type App } from "./fold";
import { Releases } from "./releases";

export function AppOverview({ app, kind, base, served, names, onChanged }: { app: App; kind: "code" | "studio"; base: string; served: number; names: ReadonlyMap<string, string>; onChanged: () => void }): ReactNode {
  const credentials = useCredentials();
  const counted = useInsights(30, { agent: app.agent });
  const rehearsed = useInsights(30, { agent: app.agent, world: "sandbox" });
  const [report, setReport] = useState<Report | null>(null);

  // An app's turn and its minute are measured on its overview; a Studio agent's on Configure, beside what it runs on.
  useEffect(() => {
    if (kind !== "code") return undefined;
    let gone = false;
    readReport(credentials, app.agent).then((read) => !gone && setReport(read), () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials, app.agent, kind]);
  const said = saidOf(app);
  const { hosted, held } = app;

  const series = counted?.series ?? [];
  const calls: Point[] = series.map((day) => ({ label: dayLabel(day.day), value: callsOf(day), detail: `${day.phone} phone, ${day.web} web, ${day.whatsapp} WhatsApp` }));
  const total = counted?.conversations.now ?? 0;
  const judged = counted?.judged ?? 0;
  const passed = counted?.passed ?? 0;
  const channels = counted?.channels;

  const failed = hosted?.failed_why != null && (
    <section className="app-failed" aria-label="Why it failed">
      <span className="app-failed-title">Release {hosted.release} did not start</span>
      <pre className="app-logs">{hosted.failed_why}</pre>
    </section>
  );
  // An app of several agents has no calls of its own: each agent's are on its own page, a row under the app's.
  if (isOfAgents(app)) {
    return (
      <div className="app-panel">
        {failed}
        <section className="dash-card" aria-label="Its agents">
          <div className="dash-card-top">
            <span className="dash-eyebrow">Agents</span>
          </div>
          <p className="dash-quiet app-note">The calls, the tests, the channels and the settings are each agent's own.</p>
          <div className="app-members">
            {app.agents.map((slug) => (
              <Link key={slug} to={`${base}/${encodeURIComponent(slug)}`} className="app-member">
                <Avatar kind={kind} name={slug} size={24} />
                <span className="dash-clip">{slug}</span>
              </Link>
            ))}
          </div>
        </section>
        <section className="dash-card" aria-label="How it is running">
          <div className="dash-parts cfg-parts-flush">
            <Part
              title="Running"
              value={hosted === null ? said.where : hosted.live_release === null ? "Not serving" : `Release ${hosted.live_release}`}
              under={hosted === null ? "Connected to the gateway" : `Deployed by ${whoIs(names, hosted.created_by)}`}
              facts={[
                { name: "Served", value: hosted === null ? "—" : hours(served) },
                { name: "World", value: WORLD === "sandbox" ? "Sandbox" : "Production" },
                { name: "Agents", value: String(app.agents.length) },
              ]}
            />
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="app-panel">
      {failed}

      <section className="dash-card app-headlines" aria-label="The last 30 days">
        <Ring
          title="Calls"
          figure={counted === null ? "—" : count(total)}
          note="in 30 days"
          slices={[
            { name: "Phone", value: channels?.phone ?? 0, tone: "accent", shown: count(channels?.phone ?? 0) },
            { name: "Web", value: channels?.web ?? 0, tone: "blue", shown: count(channels?.web ?? 0) },
            { name: "WhatsApp", value: channels?.whatsapp ?? 0, tone: "good", shown: count(channels?.whatsapp ?? 0) },
          ]}
        />
        <Ring
          title="Held by the judges"
          figure={judged === 0 ? "—" : percent(passed / judged)}
          note={`of ${judged} judged`}
          slices={[
            { name: "Held", value: passed, tone: "good", shown: count(passed) },
            { name: "Broke", value: judged - passed, tone: "warn", shown: count(judged - passed) },
          ]}
        />
      </section>

      {kind === "code" && report !== null && <MeasuresCard report={report} measuring={measuringOf(app.agent, report, counted, rehearsed)} />}

      <section className="dash-card" aria-label="How it is running">
        <div className="dash-parts cfg-parts-flush">
          <Part
            title="Running"
            value={hosted === null ? said.where : hosted.live_release === null ? "Not serving" : `Release ${hosted.live_release}`}
            under={hosted === null ? "Connected to the gateway" : `Deployed by ${whoIs(names, hosted.created_by)}`}
            facts={[
              { name: "Served", value: hosted === null ? "—" : hours(served) },
              { name: "World", value: WORLD === "sandbox" ? "Sandbox" : "Production" },
              { name: "Channels", value: held === null ? "—" : String(held.channels.length) },
            ]}
          />
          <Part
            title="Answers"
            value={counted?.median_e2e_s == null ? "—" : seconds(counted.median_e2e_s)}
            under="Median time to answer"
            facts={[
              { name: "Resolved", value: counted?.resolved_rate == null ? "—" : percent(counted.resolved_rate) },
              { name: "Avg length", value: counted?.mean_length_s == null ? "—" : `${Math.round(counted.mean_length_s)} s` },
              { name: "To a person", value: counted === null ? "—" : count(counted.escalated) },
            ]}
          />
          <Part
            title="Spend"
            value={counted === null ? "—" : money(counted.spend_usd)}
            under="In 30 days"
            facts={[
              { name: "Per call", value: counted === null || total === 0 ? "—" : money(counted.spend_usd / total) },
              { name: "Judged", value: count(judged) },
              { name: "Held", value: count(passed) },
            ]}
          />
        </div>
      </section>

      <section className="dash-card" aria-label="Calls a day">
        <div className="dash-card-top">
          <span className="dash-eyebrow">Calls a day</span>
        </div>
        <DayChart kind="area" points={calls} tone="accent" atLeast={2} said={(value) => count(Math.round(value))} nothing="No calls in these days." />
      </section>

      {kind === "studio" && hosted !== null && <Releases key={`${app.name}:${hosted.release ?? 0}`} app={hosted} names={names} onRolledBack={onChanged} />}
    </div>
  );
}
