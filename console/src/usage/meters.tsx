/** The org's quotas as two sections of meter tiles: what is metered a month, and what it holds now. */

import type { ReactNode } from "react";

import { Icon, type IconName } from "../shell/icons";
import type { Limits } from "./door";
import { HELD, meterOf, MONTHLY, type Meter, type MeterKey } from "./fold";
import "../dashboard/dashboard.css";
import "../test/test.css";
import "./usage.css";

const ICONS: Readonly<Record<string, IconName>> = {
  minutes: "clock",
  messages: "chat",
  llm_tokens: "type",
  evals: "judges",
  simulations: "simulations",
  budget_usd: "coins",
  agents: "agents",
  seats: "team",
  numbers: "numbers",
  hosted_apps: "apps",
  memory_facts: "brain",
  knowledge_chunks: "knowledge",
  concurrent_calls: "wave",
};

/** A thin bar: the share filled in the section's colour, amber past 80%, red when full. */
export function ShareBar({ share, mood = "calm" }: { share: number; mood?: Meter["mood"] }): ReactNode {
  const filled = Math.min(1, Math.max(0, share));
  return (
    <span className="tst-bar usg-bar" aria-hidden="true">
      {filled > 0 && <i className={`usg-fill usg-fill-${mood}`} style={{ flexGrow: filled }} />}
      {filled < 1 && <i className="tst-bar-none" style={{ flexGrow: 1 - filled }} />}
    </span>
  );
}

function MeterTile({ meter }: { meter: Meter }): ReactNode {
  return (
    <div className="usg-meter">
      <span className="usg-meter-name">
        <Icon name={ICONS[meter.key] ?? "gauge"} size={14} />
        <span className="dash-clip">{meter.name}</span>
      </span>
      <span className={`usg-meter-value usg-value-${meter.mood}`}>
        {meter.used}
        <span className="usg-of">{meter.limit === null ? "no limit" : `of ${meter.limit}`}</span>
      </span>
      {meter.share !== null && <ShareBar share={meter.share} mood={meter.mood} />}
      <span className="dash-quiet dash-clip">{meter.about}</span>
    </div>
  );
}

function Section({ tone, icon, title, about, keys, limits }: { tone: string; icon: IconName; title: string; about: string; keys: readonly MeterKey[]; limits: Limits | null }): ReactNode {
  const meters = limits === null ? [] : keys.map((key) => meterOf(key, limits));
  const full = meters.filter((meter) => meter.mood === "bad").length;
  return (
    <section className={`tst-list ${tone}`} aria-label={title}>
      <header className="tst-head">
        <span className="tst-head-mark" aria-hidden="true">
          <Icon name={icon} size={16} />
        </span>
        <span className="tst-head-words">
          <span className="tst-head-title">{title}</span>
          <span className="tst-head-about">{about}</span>
        </span>
        {full > 0 && <span className="tst-head-stands usg-full">{full} at the limit</span>}
      </header>
      {limits === null && <p className="dash-quiet tst-none">Reading…</p>}
      <div className="usg-meters">
        {meters.map((meter) => (
          <MeterTile key={meter.key} meter={meter} />
        ))}
      </div>
    </section>
  );
}

/** Null while the limits are being read. */
export function Meters({ limits }: { limits: Limits | null }): ReactNode {
  const month = new Date().toLocaleDateString("en-US", { month: "long", timeZone: "UTC" });
  return (
    <div className="usg-stack">
      <Section tone="tst-tone-blue" icon="clock" title="This month" about={`Metered in ${month}, UTC.`} keys={MONTHLY} limits={limits} />
      <Section tone="usg-tone-good" icon="gauge" title="Held now" about="What the org keeps." keys={HELD} limits={limits} />
    </div>
  );
}
