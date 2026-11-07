/** The setups a comparison runs the agent on: one card each, its three stages picked from what this box runs, over the agent's own. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { brandOf, doing, readCatalogue, type Catalogue, type Modality } from "../../lib/catalogue";
import { Avatar, Icon, Select, SelectItem, tintAt, type IconName } from "../../ui";
import { VoiceField } from "../settings/stages";
import { COMPARED_AT_MOST, type AgentValues } from "./comparing";

/** The three stages a setup picks, each with its icon and its name, once, beside its field. */
const STAGES: readonly { modality: Modality; label: string; icon: IconName }[] = [
  { modality: "stt", label: "Listens", icon: "ear" },
  { modality: "llm", label: "Thinks", icon: "bulb" },
  { modality: "tts", label: "Speaks", icon: "speaker" },
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
    <div className="sim-setups">
      {rows.map((row, index) => {
        const changed = STAGES.some(({ modality }) => row[modality] !== undefined);
        return (
          <div key={index} className="sim-setup">
            <div className="sim-setup-head">
              <Avatar name={`setup ${String(index + 1)}`} letters={String(index + 1)} tint={tintAt(index)} size={26} round />
              <span className="sim-setup-words">
                <span className="sim-setup-name">Setup {String(index + 1)}</span>
                <span className="sim-setup-sub">{changed ? said(row) : "Same as the agent"}</span>
              </span>
              {rows.length > 2 && (
                <button type="button" className="sim-setup-drop" onClick={() => onChange(rows.filter((_, at) => at !== index))} aria-label={`Remove setup ${String(index + 1)}`}>
                  <Icon name="cross" size={15} />
                </button>
              )}
            </div>
            <div className="sim-setup-stages">
              {STAGES.map(({ modality, label, icon }) => (
                <StagePick key={modality} catalogue={catalogue} modality={modality} label={label} icon={icon} word={row[modality]} onChange={(word) => replace(index, { ...row, [modality]: word, ...(modality === "tts" ? { voice: undefined } : {}) })} />
              ))}
            </div>
            {halves(row.tts)[0] !== "" && (
              <VoiceField vendor={halves(row.tts)[0]} providers={catalogue.providers} model={halves(row.tts)[1] || null} language={null} opening="" voice={row.voice ?? ""} onChange={(voice) => replace(index, { ...row, voice: voice === "" ? undefined : voice })} />
            )}
          </div>
        );
      })}
      {rows.length < COMPARED_AT_MOST && (
        <button type="button" className="sim-setup sim-setup-add" onClick={() => onChange([...rows, {}])}>
          <span className="sim-setup-plus" aria-hidden>
            +
          </span>
          <span className="sim-setup-name">Add a setup</span>
          <span className="sim-setup-sub">Try one more model or voice</span>
        </button>
      )}
    </div>
  );
}

// A setup in a few words: the vendors it changes, the rest left as the agent's.
function said(row: AgentValues): string {
  return STAGES.filter(({ modality }) => row[modality] !== undefined)
    .map(({ modality, label }) => `${label.toLowerCase()} with ${brandOf(halves(row[modality])[0])}`)
    .join(" · ");
}

// One stage: its icon and name beside the field, the vendors this box runs for it, and a model of the vendor's
// once one is picked; "" is the agent's own setting, said so rather than read as a choice.
function StagePick({ catalogue, modality, label, icon, word, onChange }: { catalogue: Catalogue; modality: Modality; label: string; icon: IconName; word: string | undefined; onChange: (word: string | undefined) => void }): ReactNode {
  const [vendor, model] = halves(word);
  const ready = doing(catalogue.providers, modality)
    .filter((one) => one.ready)
    .map((one) => one.name);
  const vendors = vendor === "" || ready.includes(vendor) ? ready : [vendor, ...ready];
  // The models the runtime names for this vendor, its default first; the vendors are the ones this org may run, on its own key or one the runtime lends.
  const known = catalogue.models[`${modality}/${vendor}`] ?? [];
  const runsOn = catalogue.runs[`${modality}/${vendor}`];
  const models = model === "" || known.includes(model) ? known : [model, ...known];
  return (
    <div className={vendor === "" ? "sim-stage" : "sim-stage sim-stage-changed"}>
      <span className="sim-stage-icon">
        <Icon name={icon} size={14} />
      </span>
      <span className="sim-stage-label">{label}</span>
      <Select size="sm" value={vendor} aria-label={label} onValueChange={(value) => onChange(value === "" ? undefined : value)}>
        <SelectItem value="">Same as the agent</SelectItem>
        {vendors.map((name) => (
          <SelectItem key={name} value={name}>
            {brandOf(name)}
          </SelectItem>
        ))}
      </Select>
      {vendor !== "" && known.length > 0 && (
        <div className="sim-stage-model">
          <Select size="sm" value={model} aria-label={`${label}: model`} onValueChange={(value) => onChange(value === "" ? vendor : `${vendor}/${value}`)}>
            <SelectItem value="">{runsOn === undefined ? "Its default model" : `${runsOn} · default`}</SelectItem>
            {models.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </Select>
        </div>
      )}
    </div>
  );
}
