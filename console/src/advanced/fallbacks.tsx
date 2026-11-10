/** The vendors that take over a stage when the one it runs on fails, in order: added from the ones the org can run, taken out one by one. */

import type { ReactNode } from "react";

import type { Provider } from "../configure/door";
import { brandOf } from "../configure/vendors";
import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { Mark } from "../ui/setting";

export function Fallbacks({ label, modality, providers, running, value, disabled, onChange }: { label: string; modality: "stt" | "tts"; providers: readonly Provider[]; running: string; value: readonly string[]; disabled: boolean; onChange: (next: readonly string[]) => void }): ReactNode {
  const left = providers.filter((one) => one.does.includes(modality) && one.name !== running && !value.includes(one.name));
  const items = left.map((one) => {
    const needsAKey = one.availability === "bring your own" || (one.broken ?? null) !== null;
    return { value: one.name, label: brandOf(one.name), leading: <Mark letter={brandOf(one.name).charAt(0)} />, disabled: needsAKey, hint: needsAKey ? `Add your ${brandOf(one.name)} key to run it.` : undefined };
  });
  return (
    <div className="adv-stack">
      {value.map((word, at) => (
        <div key={word} className="adv-fallback">
          <span className="dash-quiet adv-fallback-at">{at + 1}</span>
          <Mark letter={brandOf(word.split("/")[0] ?? word).charAt(0)} />
          <span className="dash-clip adv-fallback-name" title={word}>
            {brandOf(word.split("/")[0] ?? word)}
          </span>
          {!disabled && (
            <button type="button" className="adv-fallback-drop" aria-label={`Take out ${word}`} onClick={() => onChange(value.filter((one) => one !== word))}>
              <Icon name="close" size={14} />
            </button>
          )}
        </div>
      ))}
      {!disabled && <Select items={items} value="" label={label} placeholder="Add a fallback" onChange={(picked) => onChange([...value, picked])} />}
      {disabled && value.length === 0 && <p className="dash-quiet">None: Pinecall's own, if the stage has any.</p>}
    </div>
  );
}
