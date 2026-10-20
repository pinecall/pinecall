/** The three stages of a turn as sections: the vendor and the model picked from lists, and the voice. */

import type { ReactNode } from "react";

import { doing, named, type Provider } from "../../lib/catalogue";
import { Label } from "../../ui";
import { Advanced } from "./advanced";
import { Choice, type Pick } from "./choice";
import { FixedByTheClass } from "./plugin";
import type { Knob, Modality } from "./typed";
import { VoiceById } from "./voice-by-id";
import { VoicePicker } from "./voice-picker";

const NOT_HERE = "not on this box";

export function StageSection({
  modality,
  title,
  blurb,
  knob,
  providers,
  defaults,
  models,
  onChange,
  fixed,
  unset,
  own,
  children,
  advanced,
}: {
  modality: Modality;
  title: string;
  blurb: string;
  knob: Knob;
  providers: readonly Provider[];
  defaults: Readonly<Record<string, string>>;
  models: Readonly<Record<string, readonly string[]>>;
  onChange: (knob: Knob) => void;
  /** Set when the agent's class declares this stage: what it runs, read-only. */
  fixed?: { value: string | null } | undefined;
  /** What no vendor picked means, where it is not the runtime's default; no model is listed until one is. */
  unset?: string | undefined;
  /** The vendors this org runs on its own key; every other is lent by the runtime. */
  own: ReadonlySet<string>;
  children?: ReactNode;
  /** What most people never touch: folded away until asked for. */
  advanced?: ReactNode;
}): ReactNode {
  if (fixed !== undefined) {
    return (
      <section className="set-section">
        <div className="set-section-head">
          <h2 className="set-section-title">{title}</h2>
          <p className="set-section-blurb">{blurb}</p>
        </div>
        <FixedByTheClass label="Vendor and model" value={fixed.value} />
        {children}
      </section>
    );
  }
  // Only what this box can run: a vendor with a key here. One with no key is a line that would go
  // out silent; one with no models listed runs its own default, which the Model row says. A vendor
  // set from the terminal that has no key still shows, said so, rather than a list that quietly
  // reads as "nothing chosen".
  const ready = doing(providers, modality).filter((one) => one.ready);
  const runtimeDefault = defaults[modality] ?? "";
  const vendor = knob.vendor === "" ? runtimeDefault : knob.vendor;
  const listed = ready.some((one) => one.name === knob.vendor) ? ready : knob.vendor === "" ? ready : [{ name: knob.vendor, ready: false } as Provider, ...ready];
  const known = models[`${modality}/${vendor}`] ?? [];
  const options = known.includes(knob.model) || knob.model === "" ? known : [knob.model, ...known];
  const vendors: Pick[] = [
    { value: "", label: unset ?? "Runtime default", tag: unset === undefined ? runtimeDefault : undefined },
    ...listed.map((one) => ({ value: one.name, label: one.name, mono: true, tag: !one.ready ? NOT_HERE : own.has(one.name) ? "your key" : "lent by the runtime" })),
  ];
  const picks: Pick[] = [
    { value: "", label: `${vendor}'s default`, tag: known[0] },
    ...options.map((name) => ({ value: name, label: name, mono: true, tag: known.includes(name) ? undefined : "as set" })),
  ];
  return (
    <section className="set-section">
      <div className="set-section-head">
        <h2 className="set-section-title">{title}</h2>
        <p className="set-section-blurb">{blurb}</p>
      </div>
      <div className="set-field">
        <Label>Vendor</Label>
        <Choice label="Vendor" picks={vendors} value={knob.vendor} onPick={(value) => onChange({ vendor: value, model: "" })} />
        <p className="set-help">Only vendors this box has a key for. Add one in Providers.</p>
      </div>
      {(unset === undefined || knob.vendor !== "") && (
        <div className="set-field">
          <Label>Model</Label>
          {known.length === 0 ? (
            <p className="set-help">{vendor} runs its own default; there is no model to pick.</p>
          ) : (
            <>
              <Choice label="Model" picks={picks} value={knob.model} onPick={(value) => onChange({ ...knob, model: value })} />
              <p className="set-help">The default is the one tuned for phone calls.</p>
            </>
          )}
        </div>
      )}
      {children}
      {advanced !== undefined && advanced !== null && advanced !== false && <Advanced>{advanced}</Advanced>}
    </section>
  );
}

/** The voice: picked by ear from the vendor's own list where the gateway lists one; any other vendor speaks in an id set from the terminal. */
export function VoiceField({
  vendor,
  providers,
  model,
  language,
  opening,
  voice,
  onChange,
}: {
  /** The vendor that speaks, or null while the report that says which is still being asked for. */
  vendor: string | null;
  providers: readonly Provider[];
  model: string | null;
  language: string | null;
  opening: string;
  voice: string;
  onChange: (voice: string) => void;
}): ReactNode {
  // Which vendors list their voices is the catalogue row's word (voices_listed), never a list
  // kept here: the picker that mounted for the wrong vendor while the report was on its way asked
  // the gateway for a list nobody was going to read.
  if (vendor === null) return <VoiceNote>Asking the gateway which vendor speaks…</VoiceNote>;
  if (named(providers, vendor)?.voices_listed === true) return <VoicePicker vendor={vendor} model={model} language={language} opening={opening} voice={voice} onChange={onChange} />;
  return (
    <div className="set-row">
      <div className="set-field">
        <Label>Voice</Label>
        <p className="set-help">
          {voice === "" ? `${vendor} speaks in its model's own voice.` : `${vendor} speaks as ${voice}.`} {vendor} lists no voices here: write the id {vendor} gives the one you want, listen to it, and use it.
        </p>
        <VoiceById vendor={vendor} model={model} language={language} opening={opening} voice={voice} onChange={onChange} label="A voice by its id" />
      </div>
    </div>
  );
}

function VoiceNote({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="set-row">
      <div className="set-field">
        <Label>Voice</Label>
        <p className="set-help">{children}</p>
      </div>
    </div>
  );
}
