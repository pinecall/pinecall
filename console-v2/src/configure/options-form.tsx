/** A vendor's own options as a form: each argument its plugin takes, drawn by kind, with the plugin's default shown and a JSON view beside it. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readOptions, type PluginOption, type PluginOptions } from "./door";
import { brandOf, type Modality } from "./vendors";

export type Options = Record<string, unknown>;

/** `max_completion_tokens` → "Max completion tokens". */
export function wordsOf(name: string): string {
  const spaced = name.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The value an option holds in the map, inside its object when it has one. */
export function valueOf(options: Options, option: PluginOption): unknown {
  if (option.inside === null) return options[option.name];
  const held = options[option.inside];
  return isRecord(held) ? held[option.name] : undefined;
}

/** The map with the option set, or taken out when `value` is undefined; an emptied object goes with it. */
export function withValue(options: Options, option: PluginOption, value: unknown): Options {
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

function Control({ option, value, disabled, onChange }: { option: PluginOption; value: unknown; disabled: boolean; onChange: (value: unknown) => void }): ReactNode {
  const placeholder = option.default === null || option.default === undefined ? "Plugin's default" : `Default: ${shown(option.default)}`;
  if (option.kind === "boolean") {
    const picked = value === undefined ? "" : value ? "on" : "off";
    return (
      <select className="cfg-input" aria-label={wordsOf(option.name)} value={picked} disabled={disabled} onChange={(event) => onChange(event.target.value === "" ? undefined : event.target.value === "on")}>
        <option value="">{placeholder}</option>
        <option value="on">On</option>
        <option value="off">Off</option>
      </select>
    );
  }
  if (option.kind === "choice" && !option.open) {
    return (
      <select className="cfg-input" aria-label={wordsOf(option.name)} value={shown(value)} disabled={disabled} onChange={(event) => onChange(event.target.value === "" ? undefined : event.target.value)}>
        <option value="">{placeholder}</option>
        {option.choices.map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </select>
    );
  }
  if (option.kind === "choice") {
    const list = `${option.name}-choices`;
    return (
      <>
        <input className="cfg-input" list={list} aria-label={wordsOf(option.name)} placeholder={placeholder} value={shown(value)} disabled={disabled} onChange={(event) => onChange(event.target.value === "" ? undefined : event.target.value)} />
        <datalist id={list}>
          {option.choices.map((choice) => (
            <option key={choice} value={choice} />
          ))}
        </datalist>
      </>
    );
  }
  if (option.kind === "number" || option.kind === "integer") {
    return (
      <input
        className="cfg-input"
        type="number"
        step={option.kind === "integer" ? 1 : "any"}
        aria-label={wordsOf(option.name)}
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
    return <input className="cfg-input" aria-label={wordsOf(option.name)} placeholder={placeholder === "Plugin's default" ? "Comma-separated" : placeholder} value={shown(value)} disabled={disabled} onChange={(event) => onChange(event.target.value.trim() === "" ? undefined : event.target.value.split(",").map((one) => one.trim()).filter((one) => one !== ""))} />;
  }
  if (option.kind === "json") {
    return <JsonControl option={option} value={value} disabled={disabled} onChange={onChange} />;
  }
  return <input className="cfg-input" aria-label={wordsOf(option.name)} placeholder={placeholder} value={shown(value)} disabled={disabled} spellCheck={false} onChange={(event) => onChange(event.target.value === "" ? undefined : event.target.value)} />;
}

function JsonControl({ option, value, disabled, onChange }: { option: PluginOption; value: unknown; disabled: boolean; onChange: (value: unknown) => void }): ReactNode {
  const [text, setText] = useState(value === undefined ? "" : JSON.stringify(value));
  const [bad, setBad] = useState(false);
  return (
    <input
      className={bad ? "cfg-input opt-mono opt-bad" : "cfg-input opt-mono"}
      aria-label={wordsOf(option.name)}
      placeholder='{"key": "value"}'
      value={text}
      disabled={disabled}
      spellCheck={false}
      onChange={(event) => {
        setText(event.target.value);
        if (event.target.value.trim() === "") {
          setBad(false);
          return onChange(undefined);
        }
        try {
          onChange(JSON.parse(event.target.value));
          setBad(false);
        } catch {
          setBad(true);
        }
      }}
    />
  );
}

function RawJson({ options, disabled, onChange }: { options: Options; disabled: boolean; onChange: (options: Options) => void }): ReactNode {
  const [text, setText] = useState(JSON.stringify(options, null, 2));
  const [refused, setRefused] = useState<string | null>(null);
  const apply = (): void => {
    try {
      const read: unknown = text.trim() === "" ? {} : JSON.parse(text);
      if (!isRecord(read)) return setRefused("An object of the plugin's keyword arguments.");
      setRefused(null);
      onChange(read);
    } catch (failed) {
      setRefused(failed instanceof Error ? failed.message : "Not JSON.");
    }
  };
  return (
    <div className="opt-raw">
      <textarea className="cfg-input cfg-area opt-mono" rows={Math.min(16, Math.max(5, text.split("\n").length + 1))} spellCheck={false} aria-label="Options as JSON" value={text} readOnly={disabled} onChange={(event) => setText(event.target.value)} />
      {refused !== null && <p className="cfg-refused">{refused}</p>}
      {!disabled && (
        <div className="opt-raw-foot">
          <span className="dash-quiet">The plugin's keyword arguments, as `pinecall agent set --{"{stage}"}-option` writes them.</span>
          <button type="button" className="app-button" onClick={apply}>
            Apply JSON
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * The vendor's options for a stage: what its plugin takes, each with the plugin's default as its
 * placeholder; what is typed is kept in the settings' `<stage>_options`, which run on the org's own
 * key alone. `lead` is drawn first among them: a setting of the stage's own, which needs no such key.
 */
export function OptionsForm({ modality, vendor, ownKey, options, lead, onChange }: { modality: Modality; vendor: string; ownKey: boolean; options: Options; lead: ReactNode; onChange: (options: Options) => void }): ReactNode {
  const credentials = useCredentials();
  const [known, setKnown] = useState<PluginOptions | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [view, setView] = useState<"form" | "json">("form");
  const touched = Object.keys(options).length;

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

  if (vendor === "") return null;
  const disabled = !ownKey;
  const groups = new Map<string | null, PluginOption[]>();
  for (const option of known?.options ?? []) groups.set(option.inside, [...(groups.get(option.inside) ?? []), option]);

  return (
    <section className="opt" aria-label={`${brandOf(vendor)} options`}>
      <div className="opt-top">
        <span className="opt-title">
          {brandOf(vendor)} options
          {touched > 0 && <span className="opt-count">{touched} set</span>}
        </span>
        <div className="dash-switch" role="tablist" aria-label="Options view">
          <button type="button" role="tab" aria-selected={view === "form"} className={view === "form" ? "dash-switch-on" : ""} onClick={() => setView("form")}>
            Form
          </button>
          <button type="button" role="tab" aria-selected={view === "json"} className={view === "json" ? "dash-switch-on" : ""} onClick={() => setView("json")}>
            JSON
          </button>
        </div>
      </div>
      <div className="opt-body">
        {view === "form" && lead}
        {disabled && <p className="dash-quiet">{brandOf(vendor)}'s own settings run on your own {brandOf(vendor)} key alone, and this agent would run on Pinecall's: add yours under the vendor, above.</p>}
        {refused !== null && <p className="cfg-refused">Could not read what {brandOf(vendor)} takes: {refused}</p>}
        {view === "json" ? (
          <RawJson key={JSON.stringify(options)} options={options} disabled={disabled} onChange={onChange} />
        ) : known === null ? (
          refused === null && <p className="dash-quiet">Reading what {brandOf(vendor)} takes…</p>
        ) : known.options.length === 0 ? (
          lead === null && <p className="dash-quiet">{brandOf(vendor)} takes nothing beyond the model and the voice.</p>
        ) : (
          [...groups.entries()].map(([inside, list]) => (
            <div key={inside ?? ""} className="opt-group">
              {inside !== null && <span className="opt-group-name">{wordsOf(inside)}</span>}
              {list.map((option) => {
                const value = valueOf(options, option);
                return (
                  <label key={option.name} className={value === undefined ? "opt-row" : "opt-row opt-row-set"}>
                    <span className="opt-row-name">
                      <span className="opt-mono">{option.name}</span>
                      {option.required && <span className="dash-quiet"> required</span>}
                    </span>
                    <Control option={option} value={value} disabled={disabled} onChange={(next) => onChange(withValue(options, option, next))} />
                  </label>
                );
              })}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
