/** Which of the deployment's vendor keys a new organization is lent: all of them, none, or the vendors and single models listed. */

import { useState, type ReactNode } from "react";

import { EditDialog } from "../configure/dialog";
import { brandOf } from "../configure/vendors";
import { Icon } from "../shell/icons";
import { Select, type SelectItem } from "../ui/select";
import { Field, Mark, Toggle } from "../ui/setting";
import { Effect } from "./settings-parts";

export type LendMode = "all" | "some" | "none";

const MODES: readonly SelectItem[] = [
  { value: "all", label: "Every vendor", detail: "Any key this deployment holds, now or later." },
  { value: "some", label: "Only some", detail: "The vendors and models you pick below." },
  { value: "none", label: "None", detail: "It runs only on keys it brings itself." },
];

/** null lends everything, an empty list nothing. */
export function modeOf(lends: readonly string[] | null | undefined): LendMode {
  if (lends === null || lends === undefined) return "all";
  return lends.length === 0 ? "none" : "some";
}

/** An entry as a person reads it: a vendor whole, or one of its models. */
export function lendSaid(entry: string): { vendor: string; model: string | null } {
  const at = entry.indexOf("/");
  return at < 0 ? { vendor: entry, model: null } : { vendor: entry.slice(0, at), model: entry.slice(at + 1) };
}

export function LendsPanel({ whom, held, lends, saving, refused, onSave, onClose }: { whom: string; held: readonly string[]; lends: readonly string[] | null; saving: boolean; refused: string | null; onSave: (lends: string[] | null) => void; onClose: () => void }): ReactNode {
  const [mode, setMode] = useState<LendMode>(modeOf(lends));
  const [entries, setEntries] = useState<string[]>([...(lends ?? [])]);
  const [vendor, setVendor] = useState("");
  const [model, setModel] = useState("");
  const models = entries.filter((entry) => entry.includes("/"));
  const tick = (entry: string, on: boolean): void => setEntries(on ? [...new Set([...entries, entry])] : entries.filter((one) => one !== entry));
  const wanted = mode === "all" ? null : mode === "none" ? [] : [...new Set(entries.map((one) => one.trim()).filter((one) => one !== ""))].sort();

  return (
    <EditDialog title="Vendors it is lent" icon="brain" about={`Whose keys the calls of ${whom} run on when it has not brought its own.`} saving={saving} refused={refused} onSave={() => onSave(wanted)} onClose={onClose}>
      <Effect>Organizations made from now on get this. The ones that exist keep what they were lent: change those on each organization.</Effect>
      <Field label="It may run on">
        <Select items={MODES} value={mode} label="It may run on" searchable={false} onChange={(picked) => setMode(picked as LendMode)} />
      </Field>
      {mode === "some" && (
        <>
          <Field label="Every model of these vendors">
            {held.length === 0 && <p className="dash-quiet">This deployment holds no vendor key yet. Add one in Provider keys.</p>}
            <div className="bxs-ticks">
              {held.map((name) => (
                <div key={name} className="bxs-tick">
                  <Mark letter={brandOf(name).charAt(0)} />
                  <span className="bxs-tick-name">{brandOf(name)}</span>
                  <Toggle on={entries.includes(name)} label={`Lend ${brandOf(name)}`} onChange={(on) => tick(name, on)} />
                </div>
              ))}
            </div>
          </Field>
          <Field label="Single models">
            <p className="dash-quiet">One model without the rest of its vendor. Its dated versions come with it.</p>
            {models.map((entry) => (
              <div key={entry} className="bxs-tick">
                <span className="bxs-tick-name bxs-code">{entry}</span>
                <button type="button" className="tst-x" aria-label={`Stop lending ${entry}`} onClick={() => tick(entry, false)}>
                  <Icon name="close" size={13} />
                </button>
              </div>
            ))}
            <div className="bxs-add">
              <Select items={held.map((name) => ({ value: name, label: brandOf(name) }))} value={vendor} label="Vendor" placeholder="Vendor" onChange={setVendor} />
              <input className="cfg-input" aria-label="Model id" placeholder="Model id" spellCheck={false} value={model} onChange={(event) => setModel(event.target.value.trim())} />
              <button
                type="button"
                className="app-button"
                disabled={vendor === "" || model === ""}
                onClick={() => {
                  tick(`${vendor}/${model}`, true);
                  setModel("");
                }}
              >
                Add
              </button>
            </div>
          </Field>
        </>
      )}
      <p className="dash-quiet">
        {mode === "all" && "A call runs on this deployment's key whenever the organization has none of its own for that vendor."}
        {mode === "none" && "A vendor the organization has no key for is refused before the call starts."}
        {mode === "some" && "Anything not picked needs a key of the organization's own. Picking nothing lends nothing."}
      </p>
    </EditDialog>
  );
}
