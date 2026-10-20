/** What the box lends an org of its own keys: everything, nothing, or the vendors and single models listed. */

import { useState, type ReactNode } from "react";

import { Button, Input, Segmented, Select, SelectItem, TextAction } from "../../ui";

type Mode = "all" | "some" | "none";

const MODES = [
  { value: "all", label: "All of the runtime's keys" },
  { value: "some", label: "Only some" },
  { value: "none", label: "None, its own keys only" },
] as const;

/** The mode a stored value is in: null lends everything, an empty list nothing. */
export function modeOf(lends: string[] | null | undefined): Mode {
  if (lends === null || lends === undefined) return "all";
  return lends.length === 0 ? "none" : "some";
}

/** The value written for a mode and the entries ticked: null, [], or the entries sorted. */
export function lendsOf(mode: Mode, entries: string[]): string[] | null {
  if (mode === "all") return null;
  if (mode === "none") return [];
  return [...new Set(entries.map((entry) => entry.trim()).filter((entry) => entry !== ""))].sort();
}

/**
 * The picker: a ticked vendor lends all its models; a listed `vendor/model` lends that model alone.
 * Choosing "Only some" and ticking nothing lends nothing, as "None" does.
 */
export function LendsPicker({
  vendors,
  lends,
  onChange,
}: {
  vendors: string[];
  lends: string[] | null;
  onChange: (lends: string[] | null) => void;
}): ReactNode {
  const [mode, setMode] = useState<Mode>(modeOf(lends));
  const [vendor, setVendor] = useState("");
  const [model, setModel] = useState("");
  const entries = lends ?? [];
  const models = entries.filter((entry) => entry.includes("/"));

  const pick = (next: Mode): void => {
    setMode(next);
    onChange(lendsOf(next, next === "some" ? entries : []));
  };
  const tick = (name: string, on: boolean): void => {
    onChange(lendsOf("some", on ? [...entries, name] : entries.filter((entry) => entry !== name)));
  };

  return (
    <div className="box-lends">
      <Segmented options={MODES} value={mode} onChange={pick} />
      {mode === "some" && (
        <>
          <div className="box-caption">Every model of these vendors</div>
          <div className="box-lends-vendors">
            {vendors.length === 0 && <span className="ui-note">The runtime holds no vendor key yet: add one in Box settings → Keys.</span>}
            {vendors.map((name) => (
              <label key={name} className="box-lends-vendor">
                <input type="checkbox" checked={entries.includes(name)} onChange={(event) => tick(name, event.target.checked)} />
                {name}
              </label>
            ))}
          </div>
          <div className="box-caption">Only these models, of any other vendor</div>
          {models.length === 0 && <span className="ui-note">None. Add one below to allow a single model without the rest of its vendor.</span>}
          {models.map((entry) => (
            <div key={entry} className="box-key-row">
              <span className="box-mono">{entry}</span>
              <TextAction danger onClick={() => tick(entry, false)}>
                Remove
              </TextAction>
            </div>
          ))}
          <div className="box-lends-add">
            <Select value={vendor} onValueChange={setVendor} placeholder="Vendor…">
              {vendors.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </Select>
            <Input value={model} placeholder="model, e.g. claude-haiku-5-5" onChange={(event) => setModel(event.target.value.trim())} />
            <Button
              size="md"
              disabled={vendor === "" || model === ""}
              onClick={() => {
                tick(`${vendor}/${model}`, true);
                setModel("");
              }}
            >
              Add model
            </Button>
          </div>
        </>
      )}
      <div className="box-limit-about">
        {mode === "all" && "Whenever the org has no key of its own for a vendor, the call runs on the runtime's key."}
        {mode === "none" && "Calls run only on the org's own keys. A vendor it has no key for is refused."}
        {mode === "some" && "Only what is ticked or listed runs on the runtime's key. Anything else needs a key of the org's own."}
      </div>
    </div>
  );
}
