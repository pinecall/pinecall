/** A vendor's settings for a stage: those of its plugin's arguments the console lets a person change, each with its name, a sentence and its control. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Select } from "../ui/select";
import { Fold, Setting, Slider, Toggle } from "../ui/setting";
import { readOptions, type PluginOption, type PluginOptions } from "./door";
import { KNOBS, type Knob } from "./knobs";
import { brandOf, type Modality } from "./vendors";

export type Options = Record<string, unknown>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The value an option holds in the map, inside its object when it has one. */
function valueOf(options: Options, option: PluginOption): unknown {
  if (option.inside === null) return options[option.name];
  const held = options[option.inside];
  return isRecord(held) ? held[option.name] : undefined;
}

/** The map with the option set, or taken out when `value` is undefined; an emptied object goes with it. */
function withValue(options: Options, option: PluginOption, value: unknown): Options {
  const next = { ...options };
  if (option.inside === null) {
    if (value === undefined) delete next[option.name];
    else next[option.name] = value;
    return next;
  }
  const held = isRecord(next[option.inside]) ? { ...(next[option.inside] as Record<string, unknown>) } : {};
  if (value === undefined) delete held[option.name];
  else held[option.name] = value;
  if (Object.keys(held).length === 0) delete next[option.inside];
  else next[option.inside] = held;
  return next;
}

function shown(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(String).join(", ");
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** `ENDPOINTING_SENSITIVITY_SHORT` beside its siblings → "Short"; `min_latency` → "Min latency". */
function choiceWords(choice: string, siblings: readonly string[]): string {
  let shared = 0;
  const first = siblings[0] ?? "";
  while (siblings.length > 1 && shared < first.length && siblings.every((one) => one[shared] === first[shared])) shared += 1;
  const cut = first.lastIndexOf("_", shared) + 1;
  const spaced = (siblings.length > 1 ? choice.slice(cut) : choice).replace(/[_-]/g, " ").toLowerCase().trim();
  return spaced === "" ? choice : spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function ChoiceControl({ option, title, value, disabled, onChange }: { option: PluginOption; title: string; value: unknown; disabled: boolean; onChange: (value: unknown) => void }): ReactNode {
  const fallback = option.default === null || option.default === undefined ? "Default" : `Default (${choiceWords(shown(option.default), option.choices)})`;
  const items = [{ value: "", label: fallback }, ...option.choices.map((choice) => ({ value: choice, label: choiceWords(choice, option.choices) }))];
  return <Select items={items} value={shown(value)} label={title} disabled={disabled} searchable={false} onChange={(picked) => onChange(picked === "" ? undefined : picked)} />;
}

/** On and off where the plugin says which it is unset; else Default, On, Off, for a person is never told a state nobody knows. */
function FlagControl({ option, title, value, disabled, onChange }: { option: PluginOption; title: string; value: unknown; disabled: boolean; onChange: (value: unknown) => void }): ReactNode {
  if (typeof option.default === "boolean") {
    const fallback = option.default;
    return <Toggle on={typeof value === "boolean" ? value : fallback} label={title} disabled={disabled} onChange={(on) => onChange(on === fallback ? undefined : on)} />;
  }
  const picked = value === undefined ? "" : value ? "on" : "off";
  const words: readonly [string, string][] = [["", "Default"], ["on", "On"], ["off", "Off"]];
  return (
    <div className="dash-switch" role="tablist" aria-label={title}>
      {words.map(([word, label]) => (
        <button key={word} type="button" role="tab" aria-selected={picked === word} disabled={disabled} className={picked === word ? "dash-switch-on" : ""} onClick={() => onChange(word === "" ? undefined : word === "on")}>
          {label}
        </button>
      ))}
    </div>
  );
}

function FieldControl({ option, knob, value, disabled, onChange }: { option: PluginOption; knob: Knob; value: unknown; disabled: boolean; onChange: (value: unknown) => void }): ReactNode {
  const placeholder = option.default === null || option.default === undefined ? "Default" : shown(option.default);
  if (option.kind === "choice") return <ChoiceControl option={option} title={knob.title} value={value} disabled={disabled} onChange={onChange} />;
  if ((option.kind === "number" || option.kind === "integer") && knob.range !== undefined) {
    const range = knob.range;
    return <Slider value={shown(value)} label={knob.title} min={range.min} max={range.max} step={range.step} rest={range.rest} ends={range.ends} disabled={disabled} onChange={(typed) => onChange(typed === "" ? undefined : Number(typed))} />;
  }
  if (option.kind === "number" || option.kind === "integer") {
    return (
      <input
        className="cfg-input"
        type="number"
        step={option.kind === "integer" ? 1 : "any"}
        aria-label={knob.title}
        placeholder={placeholder}
        value={value === undefined ? "" : String(value)}
        disabled={disabled}
        onChange={(event) => {
          const typed = event.target.value;
          if (typed === "") return onChange(undefined);
          const number = option.kind === "integer" ? Number.parseInt(typed, 10) : Number(typed);
          if (Number.isFinite(number)) onChange(number);
        }}
      />
    );
  }
  if (option.kind === "list") {
    return <input className="cfg-input" aria-label={knob.title} placeholder="Separated by commas" value={shown(value)} disabled={disabled} onChange={(event) => onChange(event.target.value.trim() === "" ? undefined : event.target.value.split(",").map((one) => one.trim()).filter((one) => one !== ""))} />;
  }
  return <input className="cfg-input" aria-label={knob.title} placeholder={placeholder} value={shown(value)} disabled={disabled} spellCheck={false} onChange={(event) => onChange(event.target.value === "" ? undefined : event.target.value)} />;
}

/**
 * What the vendor lets a person change here: its plugin's arguments the console names (`knobs.ts`), any
 * other the settings already hold going back as it was. They run on the org's own key alone; `lead` is
 * drawn first among them, a setting of the stage's own, which needs no such key.
 */
export function OptionsForm({ modality, vendor, ownKey, options, lead, onChange }: { modality: Modality; vendor: string; ownKey: boolean; options: Options; lead: ReactNode; onChange: (options: Options) => void }): ReactNode {
  const credentials = useCredentials();
  const [known, setKnown] = useState<PluginOptions | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [open, setOpen] = useState(Object.keys(options).length > 0);

  useEffect(() => {
    let gone = false;
    setKnown(null);
    setRefused(null);
    if (vendor === "") return;
    readOptions(credentials, vendor, modality, null).then(
      (read) => !gone && setKnown(read),
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials, vendor, modality]);

  const drawn = (known?.options ?? []).flatMap((option) => {
    const knob = KNOBS[modality][option.name];
    return knob === undefined ? [] : [{ option, knob }];
  });
  if (vendor === "" || (lead === null && drawn.length === 0 && refused === null)) return null;
  const brand = brandOf(vendor);
  const disabled = !ownKey;

  return (
    <>
      {lead}
      {refused !== null && <p className="cfg-refused">Could not read what {brand} takes: {refused}</p>}
      {drawn.length > 0 && <Fold title="Advanced" open={open} onToggle={() => setOpen((was) => !was)} />}
      {open && disabled && drawn.length > 0 && <p className="opt-note">These run on your own {brand} key alone. Add it under the provider to change them.</p>}
      {open &&
        drawn.map(({ option, knob }) => {
          const value = valueOf(options, option);
          const change = (next: unknown): void => onChange(withValue(options, option, next));
          return option.kind === "boolean" ? (
            <Setting key={option.name} icon={knob.icon} title={knob.title} about={knob.about} aside={<FlagControl option={option} title={knob.title} value={value} disabled={disabled} onChange={change} />} />
          ) : (
            <Setting key={option.name} icon={knob.icon} title={knob.title} about={knob.about}>
              <FieldControl option={option} knob={knob} value={value} disabled={disabled} onChange={change} />
            </Setting>
          );
        })}
    </>
  );
}
