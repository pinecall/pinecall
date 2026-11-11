/** The agent's language, picked by name: what the transcriber is told to expect, what the voice speaks, and whose "mm-hm" does not interrupt. */

import { useState, type ReactNode } from "react";

import { Select, type SelectItem } from "../ui/select";
import { Field } from "../ui/setting";
import { EditDialog } from "./dialog";

// The languages offered by name; any other is typed as its tag, and the gateway checks it with the vendors.
const TAGS: readonly string[] = ["en", "es", "pt", "fr", "de", "it", "nl", "ca", "sv", "da", "nb", "fi", "pl", "cs", "ro", "hu", "el", "tr", "ru", "uk", "ar", "he", "hi", "id", "vi", "th", "ja", "ko", "zh"];
const NAMES = new Intl.DisplayNames(["en"], { type: "language" });
const OTHER = "other";

/** A tag's name in English ("es" is Spanish), or null for a tag this browser cannot name. */
export function languageName(tag: string): string | null {
  try {
    const name = NAMES.of(tag);
    return name === undefined || name.toLowerCase() === tag.toLowerCase() ? null : name;
  } catch {
    return null;
  }
}

export function LanguageEditor({ initial, ears, voice, saving, refused, onClose, onSave }: { initial: string; ears: string; voice: string; saving: boolean; refused: string | null; onClose: () => void; onSave: (tag: string) => Promise<boolean> }): ReactNode {
  const [picked, setPicked] = useState(initial === "" || TAGS.includes(initial) ? initial : OTHER);
  const [typed, setTyped] = useState(initial);
  const tag = picked === OTHER ? typed.trim() : picked;
  const items: SelectItem[] = [
    { value: "", label: "Not set", detail: `${ears} and ${voice} each run their own default.` },
    ...TAGS.map((one) => ({ value: one, label: languageName(one) ?? one, tags: <span className="cfg-tag">{one}</span>, keywords: one })),
    { value: OTHER, label: "Another language…", detail: "One not listed here, by its tag: gl, eu, sw." },
  ];
  return (
    <EditDialog title="Language" icon="chat" about="The one language this agent's calls are held in." saving={saving} refused={refused} onClose={onClose} onSave={() => void onSave(tag)}>
      <Field label="Language">
        <Select items={items} value={picked} label="Language" searchable searchPlaceholder="Search languages" onChange={setPicked} />
      </Field>
      {picked === OTHER && (
        <label className="cfg-field">
          A language tag
          <input className="cfg-input" value={typed} autoFocus spellCheck={false} placeholder="gl" onChange={(event) => setTyped(event.target.value)} />
          {tag !== "" && <span className="dash-quiet">{languageName(tag) ?? "This browser knows no language of that tag; the gateway checks it."}</span>}
        </label>
      )}
      <dl className="cfg-reach">
        <dt>What it reaches</dt>
        <dd>
          <b>The transcriber.</b> {tag === "" ? `${ears} listens in its own default language.` : `${ears} is told to expect ${languageName(tag) ?? tag}.`}
        </dd>
        <dd>
          <b>The voice.</b> {tag === "" ? `${voice} speaks its own default language.` : `${voice} speaks it, and a voice nobody picked is that language's default.`}
        </dd>
        <dd>
          <b>Interruptions.</b> {tag === "" ? "A short agreement in any language Pinecall knows does not stop the agent." : "A short agreement in that language, a “yes” or an “mm-hm”, does not stop the agent."}
        </dd>
      </dl>
    </EditDialog>
  );
}
