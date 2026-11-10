/** One org's monthly limits in one environment, typed again by the operator: the whole set replaced, its lends and its simulations' shape kept. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { EditDialog } from "../configure/dialog";
import { saveQuotas, type OneOrg, type World } from "./door";
import { LimitFields, typedLimit } from "./limit-fields";
import { QUOTAS } from "./settings-door";
import { Effect } from "./settings-parts";

// The spend cap is the door's own field, beside the limits and not among them.
const BUDGET = "budget_usd";

export function OrgLimitsPanel({ org, world, worldName, onSaved, onClose }: { org: OneOrg; world: World; worldName: string; onSaved: () => Promise<void>; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const standing = org.quotas[world];
  const [typed, setTyped] = useState<Record<string, string>>(() => Object.fromEntries(QUOTAS.map((name) => [name, (name === BUDGET ? standing?.budget_usd : standing?.limits[name])?.toString() ?? ""])));
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const save = async (): Promise<void> => {
    setSaving(true);
    setRefused(null);
    try {
      await saveQuotas(credentials, org.slug, world, {
        limits: Object.fromEntries(QUOTAS.filter((name) => name !== BUDGET).map((name) => [name, typedLimit(typed[name])])),
        budget_usd: typedLimit(typed[BUDGET]),
        // The door replaces the set whole: the keys the org is lent go back as they stand.
        lends: standing?.lends ?? null,
      });
      await onSaved();
      onClose();
    } catch (failed) {
      setRefused(saidBy(failed));
      setSaving(false);
    }
  };

  return (
    <EditDialog title={`Limits in ${worldName}`} icon="gauge" about={`What ${org.name} may use in ${worldName.toLowerCase()}.`} saving={saving} refused={refused} onSave={() => void save()} onClose={onClose}>
      <Effect>They hold from the next call and the next agent that registers. The keys it is lent and how its simulations are shaped stay as they are. Billing writes these limits too: an org on a plan gets its plan's back the next time billing writes them.</Effect>
      <p className="dash-quiet">Leave a field empty for no limit. Type 0 to switch that thing off.</p>
      <LimitFields names={QUOTAS} typed={typed} placeholder="No limit" onType={setTyped} />
    </EditDialog>
  );
}
