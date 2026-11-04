/** The voices and models a comparison runs the agent on: one row each, picked from what this box runs, over the agent's own. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { doing, readCatalogue, type Catalogue, type Modality } from "../../lib/catalogue";
import { Button, Input, Select, SelectItem } from "../../ui";
import { VoiceField } from "../settings/stages";
import { COMPARED_AT_MOST, type AgentValues } from "./comparing";

/** The three stages a row picks, each as the person reads it. */
const STAGES: readonly { modality: Modality; label: string }[] = [
  { modality: "stt", label: "Hears" },
  { modality: "llm", label: "Thinks" },
  { modality: "tts", label: "Speaks" },
];

/** `vendor/model` as its two halves; a vendor alone has no model. */
function halves(word: string | undefined): [string, string] {
  if (word === undefined) return ["", ""];
  const at = word.indexOf("/");
  return at < 0 ? [word, ""] : [word.slice(0, at), word.slice(at + 1)];
}

/** Two rows to begin with: a comparison of one is a simulation. */
export function twoRows(): AgentValues[] {
  return [{}, {}];
}

export function AgainstRows({ rows, onChange }: { rows: AgentValues[]; onChange: (rows: AgentValues[]) => void }): ReactNode {
  const credentials = useCredentials();
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    readCatalogue(credentials).then(
      (read) => live && setCatalogue(read),
      (failed: unknown) => live && setRefused(saidBy(failed)),
    );
    return () => {
      live = false;
    };
  }, [credentials]);

  if (catalogue === null) return <p className="sim-note">{refused ?? "Asking the gateway what this box runs…"}</p>;
  const replace = (index: number, values: AgentValues): void => onChange(rows.map((row, at) => (at === index ? values : row)));
  return (
    <div className="sims-cmp-rows">
      {rows.map((row, index) => (
        <div key={index} className="sims-cmp-row">
          <span className="sims-cmp-n">{String(index + 1)}</span>
          <div className="sims-cmp-stages">
            {STAGES.map(({ modality, label }) => (
              <StagePick key={modality} catalogue={catalogue} modality={modality} label={label} word={row[modality]} onChange={(word) => replace(index, { ...row, [modality]: word, ...(modality === "tts" ? { voice: undefined } : {}) })} />
            ))}
            {halves(row.tts)[0] !== "" && (
              <VoiceField vendor={halves(row.tts)[0]} providers={catalogue.providers} model={halves(row.tts)[1] || null} language={null} opening="" voice={row.voice ?? ""} onChange={(voice) => replace(index, { ...row, voice: voice === "" ? undefined : voice })} />
            )}
          </div>
          <button type="button" className="sim-link" disabled={rows.length <= 2} onClick={() => onChange(rows.filter((_, at) => at !== index))} aria-label={`Remove configuration ${String(index + 1)}`}>
            Remove
          </button>
        </div>
      ))}
      <div className="sims-cmp-add">
        <Button size="sm" disabled={rows.length >= COMPARED_AT_MOST} onClick={() => onChange([...rows, {}])}>
          Add a configuration
        </Button>
        <span className="sim-note">Up to {String(COMPARED_AT_MOST)}. A stage left as is runs the agent&apos;s own setting.</span>
      </div>
    </div>
  );
}

// One stage: the vendor from those this box runs for it, and a model of the vendor's when one is
// picked; "" is the agent's own setting, said so rather than read as a choice.
function StagePick({ catalogue, modality, label, word, onChange }: { catalogue: Catalogue; modality: Modality; label: string; word: string | undefined; onChange: (word: string | undefined) => void }): ReactNode {
  const [vendor, model] = halves(word);
  const ready = doing(catalogue.providers, modality)
    .filter((one) => one.ready)
    .map((one) => one.name);
  const vendors = vendor === "" || ready.includes(vendor) ? ready : [vendor, ...ready];
  const known = catalogue.models[`${modality}/${vendor}`]?.[0];
  return (
    <div className="sims-cmp-stage">
      <Select size="sm" value={vendor} aria-label={`${label}: vendor`} onValueChange={(value) => onChange(value === "" ? undefined : value)}>
        <SelectItem value="">{label}: the agent&apos;s own</SelectItem>
        {vendors.map((name) => (
          <SelectItem key={name} value={name}>
            {label}: {name}
          </SelectItem>
        ))}
      </Select>
      {vendor !== "" && (
        <Input
          size="sm"
          value={model}
          spellCheck={false}
          aria-label={`${label}: model`}
          placeholder={known === undefined ? `${vendor}'s default` : known}
          onChange={(event) => onChange(event.target.value.trim() === "" ? vendor : `${vendor}/${event.target.value.trim()}`)}
        />
      )}
    </div>
  );
}
