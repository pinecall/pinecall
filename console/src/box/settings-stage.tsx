/** A default stage picked: its vendor and model as selects, who takes over when it fails, and, for the judge and the simulated caller, what one call may spend. */

import { useState, type ReactNode } from "react";

import { EditDialog } from "../configure/dialog";
import { brandOf } from "../configure/vendors";
import { Icon, type IconName } from "../shell/icons";
import { Select, type SelectItem } from "../ui/select";
import { Field, Mark, Setting, Toggle } from "../ui/setting";
import type { Catalogue, Stage, StageName } from "./settings-door";
import { Effect } from "./settings-parts";

/** What the pickers know: the vendors this runtime has, the ones the deployment holds a key for, and models' names. */
export interface Known {
  catalogue: Catalogue | undefined;
  held: readonly string[];
  names: Readonly<Record<string, string>>;
}

const OTHER = "\u0000another";

export function modelSaid(known: Known, stage: Stage): string {
  return stage.model == null || stage.model === "" ? "its usual model" : (known.names[`${stage.vendor}/${stage.model}`] ?? stage.model);
}

/** `Google · Gemini 3.5 Flash Lite`. */
export function stageSaid(known: Known, stage: Stage): string {
  return `${brandOf(stage.vendor)} · ${modelSaid(known, stage)}`;
}

/** The vendor and its model. A vendor the deployment holds no key for is offered, and marked. */
export function StagePick({ modality, stage, known, onChange }: { modality: StageName; stage: Stage; known: Known; onChange: (stage: Stage) => void }): ReactNode {
  const [typing, setTyping] = useState(false);
  const offered = (known.catalogue?.providers ?? []).filter((one) => one.does.includes(modality)).map((one) => one.name);
  const every = stage.vendor === "" || offered.includes(stage.vendor) ? offered : [stage.vendor, ...offered];
  const has = (name: string): boolean => known.held.includes(name);
  const vendors: SelectItem[] = [...every]
    .sort((one, other) => Number(has(other)) - Number(has(one)) || brandOf(one).localeCompare(brandOf(other)))
    .map((name) => ({ value: name, label: brandOf(name), detail: has(name) ? "This deployment holds its key" : "No key here: only an organization with its own runs it", group: has(name) ? "Ready" : "No key here", keywords: name, leading: <Mark letter={brandOf(name).charAt(0)} /> }));

  const model = stage.model ?? "";
  const listed = known.catalogue?.models[`${modality}/${stage.vendor}`] ?? [];
  const all = model === "" || listed.includes(model) ? listed : [model, ...listed];
  const runs = known.catalogue?.runs[`${modality}/${stage.vendor}`];
  const models: SelectItem[] = [
    { value: "", label: "The vendor's usual model", detail: runs === undefined ? undefined : (known.names[`${stage.vendor}/${runs}`] ?? runs) },
    ...all.map((one) => ({ value: one, label: known.names[`${stage.vendor}/${one}`] ?? one, detail: known.names[`${stage.vendor}/${one}`] === undefined ? undefined : one, keywords: one })),
    { value: OTHER, label: "Another model…", detail: "Type its id as the vendor writes it." },
  ];

  return (
    <>
      <Field label="Vendor">
        <Select items={vendors} value={stage.vendor} label="Vendor" placeholder="Choose a vendor" searchPlaceholder="Search vendors" onChange={(vendor) => (setTyping(false), onChange({ ...stage, vendor, model: null }))} />
        {stage.vendor !== "" && !has(stage.vendor) && <p className="bxs-warn">This deployment holds no {brandOf(stage.vendor)} key. A call that falls to this default is refused, unless its organization brought its own.</p>}
      </Field>
      <Field label="Model">
        <Select items={models} value={typing ? OTHER : model} label="Model" searchPlaceholder="Search models" disabled={stage.vendor === ""} onChange={(picked) => (picked === OTHER ? setTyping(true) : (setTyping(false), onChange({ ...stage, model: picked === "" ? null : picked })))} />
        {typing && <input className="cfg-input" aria-label="Model id" placeholder="Model id" spellCheck={false} autoFocus value={model} onChange={(event) => onChange({ ...stage, model: event.target.value.trim() === "" ? null : event.target.value.trim() })} />}
      </Field>
    </>
  );
}

export function StagePanel({ title, icon, about, effect, modality, stage, known, saving, refused, onSave, onClose }: { title: string; icon: IconName; about: string; effect: string; modality: StageName; stage: Stage; known: Known; saving: boolean; refused: string | null; onSave: (stage: Stage) => void; onClose: () => void }): ReactNode {
  const [draft, setDraft] = useState<Stage>(stage);
  const [adding, setAdding] = useState<Stage | null>(null);
  const fallbacks = draft.fallbacks ?? [];
  return (
    <EditDialog title={title} icon={icon} about={about} saving={saving} refused={refused} onSave={() => onSave(draft)} onClose={onClose}>
      <Effect>{effect}</Effect>
      <StagePick modality={modality} stage={draft} known={known} onChange={setDraft} />
      <Field label="If it fails">
        <p className="dash-quiet">Who takes over, in this order, when the vendor is down or refuses. The caller hears no difference but the voice.</p>
        {fallbacks.length === 0 && adding === null && <p className="dash-quiet">Nobody. The call fails with it.</p>}
        {fallbacks.map((one, at) => (
          <div key={`${one.vendor}/${one.model ?? ""}/${at}`} className="bxs-tick">
            <span className="bxs-order">{at + 1}</span>
            <span className="bxs-tick-name">{stageSaid(known, one)}</span>
            <button type="button" className="tst-x" aria-label={`Remove ${stageSaid(known, one)}`} onClick={() => setDraft({ ...draft, fallbacks: fallbacks.filter((_, index) => index !== at) })}>
              <Icon name="close" size={13} />
            </button>
          </div>
        ))}
        {adding === null ? (
          <button type="button" className="app-button bxs-start" onClick={() => setAdding({ vendor: "" })}>
            Add a fallback
          </button>
        ) : (
          <div className="bxs-nest">
            <StagePick modality={modality} stage={adding} known={known} onChange={setAdding} />
            <div className="cfg-dialog-foot">
              <button type="button" className="app-button" onClick={() => setAdding(null)}>
                Cancel
              </button>
              <button type="button" className="app-button" disabled={adding.vendor === ""} onClick={() => (setDraft({ ...draft, fallbacks: [...fallbacks, { vendor: adding.vendor, model: adding.model ?? null }] }), setAdding(null))}>
                Add to the list
              </button>
            </div>
          </div>
        )}
      </Field>
    </EditDialog>
  );
}

export interface Spend {
  /** null runs it on the default Model. */
  llm: Stage | null;
  /** null is no cap. */
  ceiling: number | null;
}

/** The judge's model or the simulated caller's, and the most one call may spend on it. */
export function SpendPanel({ title, icon, about, effect, spend, mayFollow, mustCap, capAbout, known, saving, refused, onSave, onClose }: { title: string; icon: IconName; about: string; effect: string; spend: Spend; mayFollow: boolean; mustCap: boolean; capAbout: string; known: Known; saving: boolean; refused: string | null; onSave: (spend: Spend) => void; onClose: () => void }): ReactNode {
  const [llm, setLlm] = useState<Stage | null>(spend.llm);
  const [typed, setTyped] = useState(spend.ceiling === null ? "" : String(spend.ceiling));
  const [wrong, setWrong] = useState<string | null>(null);
  const save = (): void => {
    const ceiling = typed.trim() === "" ? null : Number(typed);
    if (ceiling !== null && (Number.isNaN(ceiling) || ceiling < 0)) return setWrong("The most it may spend is a number of dollars, like 0.05.");
    if (ceiling === null && mustCap) return setWrong("Say the most one call may spend, in dollars.");
    if (llm !== null && llm.vendor === "") return setWrong("Pick the vendor.");
    setWrong(null);
    onSave({ llm, ceiling });
  };
  return (
    <EditDialog title={title} icon={icon} about={about} saving={saving} refused={wrong ?? refused} onSave={save} onClose={onClose}>
      <Effect>{effect}</Effect>
      {mayFollow && <Setting icon="brain" title="Use the default Model" about="On, it runs on whatever the Model default is. Off, it has a model of its own." aside={<Toggle on={llm === null} label="Use the default Model" onChange={(on) => setLlm(on ? null : { vendor: "" })} />} />}
      {llm !== null && <StagePick modality="llm" stage={llm} known={known} onChange={setLlm} />}
      <Field label="Most one call may spend, in dollars">
        <input className="cfg-input" inputMode="decimal" aria-label="Most one call may spend, in dollars" placeholder={mustCap ? "0.05" : "No cap"} value={typed} onChange={(event) => setTyped(event.target.value)} />
        <p className="dash-quiet">{capAbout}</p>
      </Field>
    </EditDialog>
  );
}
