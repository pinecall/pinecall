/** The language a call is held in, picked under the STT section's vendor and model. */

import type { ReactNode } from "react";

import { Label, Select, SelectItem } from "../../ui";
import { listed } from "./conversation";

// A short list of tags and not the vendors' own: each vendor takes its own set, and a tag set from
// the terminal that is not here (`pt-BR`) is still offered, as set, so the form never drops it.
const NAMES: Readonly<Record<string, string>> = {
  en: "English",
  es: "Spanish",
  pt: "Portuguese",
  fr: "French",
  de: "German",
  it: "Italian",
};

/** The tags the field offers: the list, with a tag set elsewhere first. */
export function languagesWith(set: string): readonly string[] {
  return listed(Object.keys(NAMES), set);
}

export function LanguageField({ language, onChange }: { language: string; onChange: (language: string) => void }): ReactNode {
  return (
    <div className="set-row">
      <div className="set-field">
        <Label>Language</Label>
        <Select value={language} aria-label="Language" onValueChange={onChange}>
          <SelectItem value="">Not set — the vendor&apos;s default</SelectItem>
          {languagesWith(language).map((tag) => (
            <SelectItem key={tag} value={tag}>
              {NAMES[tag] === undefined ? `${tag} · as set` : `${NAMES[tag]} · ${tag}`}
            </SelectItem>
          ))}
        </Select>
        <p className="set-help">The language the caller is heard in and the agent speaks, handed to the vendors of the call. Not set: no language is pinned, and each vendor runs its own default.</p>
      </div>
    </div>
  );
}
