/** Box settings, the operator's: what a new organization gets, sign-in, the mailbox, the deployment's vendor keys, what an agent runs on unsaid, and the brand. */

import type { ReactNode } from "react";
import { useSearchParams } from "react-router";

import { useOrg } from "../lib/org";
import { Branding } from "../settings/branding";
import { PageHead } from "../shell/page-head";
import { SettingsAdmission } from "./settings-admission";
import { SettingsDefaults } from "./settings-defaults";
import { SettingsEmail } from "./settings-email";
import { SettingsKeys } from "./settings-keys";
import { Section } from "./settings-parts";
import { SettingsSignIn } from "./settings-signin";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "../configure/configure.css";
import "../test/test.css";
import "../numbers/numbers.css";
import "../settings/settings.css";
import "./settings.css";

const TABS = [
  { tab: "admission", name: "Admission" },
  { tab: "signin", name: "Sign-in" },
  { tab: "email", name: "Email" },
  { tab: "keys", name: "Provider keys" },
  { tab: "defaults", name: "Defaults" },
  { tab: "brand", name: "Brand" },
] as const;
type Tab = (typeof TABS)[number]["tab"];

export function BoxSettingsPage(): ReactNode {
  const { whose } = useOrg();
  const [asked, setAsked] = useSearchParams();
  // Nothing is fetched for a person who does not run the deployment: no tab is mounted.
  if (whose?.operator !== true) {
    return (
      <>
        <PageHead />
        <p className="dash-quiet bxs-calm">These are the settings of the whole deployment. They belong to the person who runs it.</p>
      </>
    );
  }
  const tab: Tab = TABS.find((one) => one.tab === asked.get("tab"))?.tab ?? "admission";
  return (
    <>
      <PageHead />
      <div className="tst bxs">
        <div className="dash-switch bxs-tabs" role="tablist" aria-label="Box settings">
          {TABS.map((one) => (
            <button key={one.tab} type="button" role="tab" aria-selected={tab === one.tab} className={tab === one.tab ? "dash-switch-on" : ""} onClick={() => setAsked(one.tab === "admission" ? {} : { tab: one.tab }, { replace: true })}>
              {one.name}
            </button>
          ))}
        </div>
        {tab === "admission" && <SettingsAdmission />}
        {tab === "signin" && <SettingsSignIn />}
        {tab === "email" && <SettingsEmail />}
        {tab === "keys" && <SettingsKeys />}
        {tab === "defaults" && <SettingsDefaults />}
        {tab === "brand" && (
          <Section icon="building" title="Brand" about="The name, logo and colour the sign-in page and every email carry, for everyone on this deployment.">
            <div className="set-brand">
              <Branding />
            </div>
          </Section>
        )}
      </div>
    </>
  );
}
