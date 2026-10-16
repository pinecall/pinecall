/** One organization for the operator: overview, members, keys, limits, providers. */

import { useCallback, useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { useWorld } from "../../lib/world";
import { Button, Page, PageHead, Refused, Tabs } from "../../ui";
import { readOrg } from "./door";
import { OrgKeys } from "./org-keys";
import { OrgLimits } from "./org-limits";
import { OrgMembers } from "./org-members";
import { OrgOverview } from "./org-overview";
import { OrgProviders } from "./org-providers";
import { saidBy, useDoor } from "./use-door";
import "./box.css";

type Tab = "overview" | "members" | "keys" | "limits" | "providers";

const TABS: readonly { tab: Tab; name: string }[] = [
  { tab: "overview", name: "Overview" },
  { tab: "members", name: "Members" },
  { tab: "keys", name: "Keys" },
  { tab: "limits", name: "Limits" },
  { tab: "providers", name: "Providers" },
];

/** The tab lives in `?tab=`. "Open as operator" asks the gateway for a key in that org. */
export function BoxOrg(): ReactNode {
  const credentials = useCredentials();
  const named = useParams()["org"] ?? "";
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.some((one) => one.tab === params.get("tab")) ? (params.get("tab") as Tab) : "overview";
  const org = useDoor(useCallback(() => readOrg(credentials, named), [credentials, named]));
  const { moveTo } = useWorld();
  const [opening, setOpening] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const open = async (id: string): Promise<void> => {
    setOpening(true);
    setRefused(null);
    try {
      await moveTo(id);
    } catch (failed) {
      setRefused(saidBy(failed));
      setOpening(false);
    }
  };

  return (
    <Page width={1060} tight>
      <PageHead
        back={
          <Link to="/box/orgs" className="box-back">
            ← Organizations
          </Link>
        }
        title={org.value?.name ?? named}
        lede={org.value === undefined ? undefined : <span className="box-fixed">{`${org.value.slug} · ${org.value.id}`}</span>}
        actions={
          org.value !== undefined && (
            <Button kind="primary" size="md" disabled={opening} onClick={() => void open(org.value?.id ?? named)}>
              {opening ? "Opening…" : "Open as operator"}
            </Button>
          )
        }
      />

      <Tabs label="Organization" tabs={TABS} on={tab} onPick={(picked) => setParams(picked === "overview" ? {} : { tab: picked })} />

      <Refused>{refused ?? org.refused}</Refused>

      {org.value !== undefined && tab === "overview" && <OrgOverview org={org.value} />}
      {tab === "members" && <OrgMembers named={named} seats={org.value?.quotas["production"]?.limits["seats"] ?? null} />}
      {tab === "keys" && <OrgKeys named={named} />}
      {org.value !== undefined && tab === "limits" && <OrgLimits org={org.value} onSaved={org.reread} />}
      {tab === "providers" && <OrgProviders named={named} />}
    </Page>
  );
}
