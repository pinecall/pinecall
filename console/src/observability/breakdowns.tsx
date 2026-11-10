/** The window broken down: by tool, by the vendor and model behind each stage, and by agent. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { ago, count, money, percent } from "../lib/format";
import type { Insights } from "../lib/insights";
import { lineOver, type Monitor, type SeriesVendor, type ToolStat } from "./door";
import { spendTotal, took, VENDOR_STAGES, vendorSaid } from "./fold";

function Head({ title, note }: { title: string; note: string }): ReactNode {
  return (
    <div className="dash-card-top ob-card-top">
      <span className="dash-eyebrow">{title}</span>
      <span className="dash-quiet ob-clip">{note}</span>
    </div>
  );
}

/** Bad when it never worked, a warning when it sometimes did not. */
function toolMood(tool: ToolStat): "good" | "warn" | "bad" {
  return tool.failed === 0 ? "good" : tool.failed >= tool.ran ? "bad" : "warn";
}

/** What each of the agent's tools did: how often it ran, how often it worked, how long it took, and the error the failing ones last said. */
export function ToolsCard({ tools }: { tools: readonly ToolStat[] }): ReactNode {
  return (
    <section className="dash-card ob-card" aria-label="Tools">
      <Head title="Tools" note="Runs, how many worked, the typical time" />
      {tools.length === 0 ? (
        <p className="dash-empty">No tool ran in these days.</p>
      ) : (
        <div className="dash-rows">
          {tools.map((tool) => {
            const mood = toolMood(tool);
            return (
              <div key={tool.name} className="ob-row dash-row">
                <span className={`app-dot app-dot-${mood}`} aria-hidden="true" />
                <span className="ob-row-main">
                  <span className="ob-mono ob-clip">{tool.name}</span>
                  {tool.last_error !== null && (
                    <Link to={`/calls/${encodeURIComponent(tool.last_error.call)}`} className="ob-row-under ob-row-link ob-clip" title={tool.last_error.text}>
                      {tool.last_error.text}, {ago(tool.last_error.at)}
                    </Link>
                  )}
                </span>
                <span className="ob-num ob-num-runs">{count(tool.ran)} runs</span>
                <span className={`ob-num dash-mood-${mood}`}>{tool.ran === 0 ? "—" : percent((tool.ran - tool.failed) / tool.ran)}</span>
                <span className="ob-num ob-num-took dash-quiet">{tool.median_s === null ? "—" : took(tool.median_s)}</span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// The one stage a monitor can watch by itself.
const STAGE_MONITOR: Readonly<Record<string, string | null>> = { stt: null, llm: "llm_median_s", tts: null };

/** Every vendor and model that answered in the window, by stage: whose key it ran on, how many turns, how fast, and whether that is past the line the org watches. */
export function VendorsCard({ vendors, own, monitors, agent }: { vendors: readonly SeriesVendor[]; own: readonly string[]; monitors: readonly Monitor[]; agent: string }): ReactNode {
  // A turn whose report named no vendor cannot be a row.
  const rows = VENDOR_STAGES.flatMap((stage) =>
    vendors
      .filter((one) => one.stage === stage.stage && one.vendor !== "")
      .sort((a, b) => b.turns - a.turns)
      .map((one) => ({ ...one, name: stage.name, tone: stage.tone })),
  );
  return (
    <section className="dash-card ob-card" aria-label="Vendors">
      <Head title="Vendors" note="Turns, the typical time, the slowest in twenty" />
      <div className="dash-rows">
        {rows.map((one) => {
          const line = lineOver(monitors, STAGE_MONITOR[one.stage] ?? null, agent);
          // Slow only past a line the org drew for that stage; with none drawn, nothing is held against it.
          const slow = line !== undefined && one.median_s !== null && one.median_s > line.threshold;
          return (
            <div key={`${one.stage}-${one.vendor}-${one.model ?? ""}`} className="ob-row dash-row">
              <span className={`ob-swatch ob-tone-${one.tone}`} aria-hidden="true" />
              <span className="ob-row-main">
                <span className="ob-clip">{vendorSaid(one.vendor, one.model)}</span>
                <span className="ob-row-under ob-clip">
                  {one.name}, {own.includes(one.vendor) ? "on your key" : "lent by the runtime"}
                </span>
              </span>
              {slow && <span className="ob-flag">Slow</span>}
              <span className="ob-num ob-num-runs dash-quiet">{count(one.turns)} turns</span>
              <span className={slow ? "ob-num dash-mood-warn" : "ob-num"}>{one.median_s === null ? "—" : took(one.median_s)}</span>
              <span className="ob-num ob-num-took dash-quiet">{one.p95_s === null ? "—" : took(one.p95_s)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Every agent that took a call in the window, the busiest first. */
export function ByAgent({ agents, said }: { agents: Insights["agents"]; said: string }): ReactNode {
  const rows = [...agents].sort((a, b) => b.calls - a.calls);
  const most = rows[0]?.calls ?? 0;
  return (
    <section className="dash-card ob-card" aria-label="By agent">
      <Head title="By agent" note={`Calls, held by the judges, spend and cost a minute in ${said}`} />
      <div className="dash-rows">
        {rows.map((one) => (
          <div key={one.slug} className="ob-row dash-row">
            <span className="ob-row-main">
              <span className="ob-row-name ob-clip">{one.slug}</span>
            </span>
            <span className="ob-share" aria-hidden="true">
              <span style={{ width: `${most === 0 ? 0 : (one.calls / most) * 100}%` }} />
            </span>
            <span className="ob-num">{count(one.calls)} calls</span>
            <span className="ob-num ob-num-runs">{one.score === null ? "—" : percent(one.score)}</span>
            <span className="ob-num">{money(spendTotal(one.spend))}</span>
            <span className="ob-num ob-num-took dash-quiet">{one.spend.per_minute_usd === null ? "—" : `$${one.spend.per_minute_usd.toFixed(3)}/min`}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
