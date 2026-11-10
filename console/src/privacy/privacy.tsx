/** Privacy, the organization's page: its rules, consent and the do-not-call list, export and erasure, and who read what, a tab each. */

import type { ReactNode } from "react";
import { useSearchParams } from "react-router";

import { PageHead } from "../shell/page-head";
import { ConsentTab } from "./consent";
import { EraseTab } from "./erase";
import { useNames } from "./parts";
import { ReadsTab } from "./reads";
import { RulesTab } from "./rules";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../apps/apps.css";
import "../test/test.css";
import "./privacy.css";

const TAB = "tab";
const TABS = [
  { id: "rules", name: "Rules" },
  { id: "consent", name: "Consent & do-not-call" },
  { id: "erase", name: "Export & erase" },
  { id: "reads", name: "Access log" },
] as const;
type TabId = (typeof TABS)[number]["id"];

/** The address says which tab is open (`?tab=`); none said, the rules. */
export function PrivacyPage(): ReactNode {
  const [params, setParams] = useSearchParams();
  const names = useNames();
  const asked = params.get(TAB);
  const tab: TabId = TABS.find((one) => one.id === asked)?.id ?? "rules";
  const open = (id: TabId): void => setParams(id === "rules" ? {} : { [TAB]: id }, { replace: true });
  return (
    <>
      <PageHead />
      <div className="tst prv-page">
        <div className="dash-switch prv-tabs" role="tablist" aria-label="Privacy">
          {TABS.map((one) => (
            <button key={one.id} type="button" role="tab" aria-selected={tab === one.id} className={tab === one.id ? "dash-switch-on" : ""} onClick={() => open(one.id)}>
              {one.name}
            </button>
          ))}
        </div>
        {tab === "rules" && <RulesTab names={names} />}
        {tab === "consent" && <ConsentTab names={names} />}
        {tab === "erase" && <EraseTab names={names} />}
        {tab === "reads" && <ReadsTab names={names} />}
      </div>
    </>
  );
}
