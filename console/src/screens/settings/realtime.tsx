/** The model a voice call runs on alone, one that hears and speaks itself, picked by vendor and model, and its options. */

import type { ReactNode } from "react";

import type { Provider } from "../../lib/catalogue";
import { Label, Select, SelectItem, TextArea } from "../../ui";
import { FixedByTheClass } from "./plugin";
import type { Knob } from "./typed";

const NOT_HERE = "not on this box";

export function RealtimeSection({
  knob,
  options,
  providers,
  realtime,
  fixed,
  onChange,
  onOptions,
}: {
  knob: Knob;
  /** Its keyword arguments as JSON text. */
  options: string;
  providers: readonly Provider[];
  /** By vendor, the models that hear and speak themselves, as the vendor's plugin names them. */
  realtime: Readonly<Record<string, readonly string[]>>;
  /** Set when the agent's class declares it: what it runs, read-only. */
  fixed?: { value: string | null } | undefined;
  onChange: (knob: Knob) => void;
  onOptions: (options: string) => void;
}): ReactNode {
  const head = (
    <div className="set-section-head">
      <h2 className="set-section-title">On voice calls</h2>
      <p className="set-section-blurb">
        A realtime model hears the caller and answers in its own voice. Picked here, the voice calls — phone and web — run on it alone, with no ears and no voice from the other tabs, and the model
        above keeps answering the written ones.
      </p>
    </div>
  );
  if (fixed !== undefined) {
    return (
      <section className="set-section">
        {head}
        <FixedByTheClass label="Realtime model" value={fixed.value} />
      </section>
    );
  }
  // Only a vendor with a key here and models of its own that hear and speak themselves; one set from
  // the terminal that is neither still shows, said so.
  const ready = providers.filter((one) => one.ready && (realtime[one.name] ?? []).length > 0).map((one) => one.name);
  const vendors = knob.vendor === "" || ready.includes(knob.vendor) ? ready : [knob.vendor, ...ready];
  const known = realtime[knob.vendor] ?? [];
  const models = knob.model === "" || known.includes(knob.model) ? known : [knob.model, ...known];
  return (
    <section className="set-section">
      {head}
      <div className="set-row">
        <div className="set-field">
          <Label>Realtime vendor</Label>
          <Select value={knob.vendor} aria-label="Realtime vendor" onValueChange={(value) => onChange({ vendor: value, model: "" })}>
            <SelectItem value="">None · the model above, with the ears and the voice</SelectItem>
            {vendors.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
                {ready.includes(name) ? "" : ` · ${NOT_HERE}`}
              </SelectItem>
            ))}
          </Select>
          <p className="set-help">
            {vendors.length === 0
              ? "No vendor with a key here has a model that hears and speaks itself. One appears once your org's key for it is added in Providers."
              : "The vendors your org has a key for whose plugin has a realtime model. It runs on your org's own key alone."}
          </p>
        </div>
        {knob.vendor !== "" && (
          <div className="set-field">
            <Label>Realtime model</Label>
            <Select value={knob.model} aria-label="Realtime model" onValueChange={(value) => onChange({ ...knob, model: value })}>
              <SelectItem value="">{knob.vendor}&apos;s own</SelectItem>
              {models.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                  {known.includes(name) ? "" : " · as set"}
                </SelectItem>
              ))}
            </Select>
            <p className="set-help">The models {knob.vendor}&apos;s plugin lists as hearing and speaking themselves.</p>
          </div>
        )}
      </div>
      {knob.vendor !== "" && (
        <div className="set-row">
          <div className="set-field set-wide">
            <Label>Realtime options</Label>
            <TextArea value={options} rows={3} aria-label="Realtime options" spellCheck={false} placeholder='{ "voice": "eve" }' onChange={(event) => onOptions(event.target.value)} />
            <p className="set-help">Its keyword arguments as JSON, named as the plugin names them: Grok&apos;s voice is voice. The call&apos;s voice tab does not reach it.</p>
          </div>
        </div>
      )}
    </section>
  );
}
