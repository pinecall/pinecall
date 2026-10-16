/** One stage of the providers row edited: the vendor, its model, and who takes over when it fails. */

import { useState, type ReactNode } from "react";

import { doing, type Catalogue, type Modality } from "../../lib/catalogue";
import { Input, Select, SelectItem } from "../../ui";
import { fallbacksOf, stageSaid, type Stage } from "./door-providers";

/**
 * Cells of the parent's grid: vendor, model, and fallbacks where asked for. A vendor the box holds no key for is
 * marked in the list: a default on it refuses every call that falls to it. The model is typed,
 * the vendor's curated ones offered.
 */
export function StageEditor({
  modality,
  stage,
  catalogue,
  held,
  withFallbacks,
  onChange,
}: {
  modality: Modality;
  stage: Stage;
  catalogue: Catalogue | null;
  held: string[];
  withFallbacks: boolean;
  onChange: (stage: Stage) => void;
}): ReactNode {
  const vendors = catalogue === null ? [] : doing(catalogue.providers, modality);
  const offered = catalogue?.models[`${modality}/${stage.vendor}`] ?? [];
  const [typed, setTyped] = useState((stage.fallbacks ?? []).map(stageSaid).join(", "));
  const listId = `box-models-${modality}`;

  return (
    <>
      <Select value={stage.vendor} onValueChange={(vendor) => onChange({ ...stage, vendor, model: null })}>
        {vendors.length === 0 && <SelectItem value={stage.vendor}>{stage.vendor}</SelectItem>}
        {vendors.map((one) => (
          <SelectItem key={one.name} value={one.name}>
            {held.includes(one.name) ? one.name : `${one.name} · no box key`}
          </SelectItem>
        ))}
      </Select>
      <Input
        list={listId}
        value={stage.model ?? ""}
        placeholder="the plugin's own model"
        onChange={(event) => onChange({ ...stage, model: event.target.value.trim() === "" ? null : event.target.value })}
      />
      <datalist id={listId}>
        {offered.map((model) => (
          <option key={model} value={model} />
        ))}
      </datalist>
      {withFallbacks && (
        <Input
          value={typed}
          placeholder="none · or vendor/model, vendor/model"
          onChange={(event) => {
            setTyped(event.target.value);
            onChange({ ...stage, fallbacks: fallbacksOf(event.target.value) });
          }}
        />
      )}
    </>
  );
}
