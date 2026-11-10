/** Settings: the org's keys, the vendors it runs on, where its traces go, how this console looks, and, for whoever runs the deployment, its brand. */

import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { chooseTheme, chosenTheme, type ThemeChoice } from "@pinecall/core/theme";
import { useOrg } from "../lib/org";
import { Icon } from "../shell/icons";
import { Branding } from "./branding";
import { Keys } from "./keys";
import { Providers } from "./providers";
import { Telemetry } from "./telemetry";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../test/test.css";
import "../numbers/numbers.css";
import "./settings.css";

type Tab = "keys" | "providers" | "telemetry" | "appearance" | "branding";

const THEMES: readonly { value: ThemeChoice; name: string; icon: "sun" | "moon" | "settings" }[] = [
  { value: "dark", name: "Dark", icon: "moon" },
  { value: "light", name: "Light", icon: "sun" },
  { value: "auto", name: "As the system", icon: "settings" },
];

function Appearance(): ReactNode {
  const [theme, setTheme] = useState<ThemeChoice>(chosenTheme);
  return (
    <section className="tst-list set-tone-accent" aria-label="Appearance">
      <header className="tst-head">
        <span className="tst-head-mark" aria-hidden="true">
          <Icon name="sun" size={16} />
        </span>
        <span className="tst-head-words">
          <span className="tst-head-title">Appearance</span>
          <span className="tst-head-about">How the console looks in this browser.</span>
        </span>
      </header>
      <div className="set-themes" role="radiogroup" aria-label="Theme">
        {THEMES.map((one) => (
          <button key={one.value} type="button" role="radio" aria-checked={theme === one.value} className={theme === one.value ? "set-theme set-theme-on" : "set-theme"} onClick={() => (chooseTheme(one.value), setTheme(one.value))}>
            <Icon name={one.icon} size={18} />
            {one.name}
          </button>
        ))}
      </div>
    </section>
  );
}

export function Settings(): ReactNode {
  const { whose } = useOrg();
  const [asked, setAsked] = useSearchParams();
  const operator = whose?.operator === true;
  const tabs: readonly { tab: Tab; name: string }[] = [
    { tab: "keys", name: "API keys" },
    { tab: "providers", name: "Providers" },
    { tab: "telemetry", name: "Telemetry" },
    { tab: "appearance", name: "Appearance" },
    ...(operator ? [{ tab: "branding" as const, name: "Branding" }] : []),
  ];
  const tab = tabs.find((one) => one.tab === asked.get("tab"))?.tab ?? "keys";
  return (
    <div className="tst set">
      <div className="dash-switch set-tabs" role="tablist" aria-label="Settings">
        {tabs.map((one) => (
          <button key={one.tab} type="button" role="tab" aria-selected={tab === one.tab} className={tab === one.tab ? "dash-switch-on" : ""} onClick={() => setAsked(one.tab === "keys" ? {} : { tab: one.tab }, { replace: true })}>
            {one.name}
          </button>
        ))}
      </div>
      {tab === "keys" && <Keys />}
      {tab === "providers" && <Providers />}
      {tab === "telemetry" && <Telemetry />}
      {tab === "appearance" && <Appearance />}
      {tab === "branding" && (
        <section className="tst-list set-tone-pink" aria-label="Branding">
          <header className="tst-head">
            <span className="tst-head-mark" aria-hidden="true">
              <Icon name="building" size={16} />
            </span>
            <span className="tst-head-words">
              <span className="tst-head-title">Branding</span>
              <span className="tst-head-about">What the sign-in page and the emails carry, for everyone on this deployment.</span>
            </span>
          </header>
          <div className="set-brand">
            <Branding />
          </div>
        </section>
      )}
    </div>
  );
}
