/** The voice a call speaks with when its agent names none, per vendor and language, each picked by ear. */

import { useCallback, useState, type ReactNode } from "react";

import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { VoicePicker } from "../configure/stage-editor";
import { brandOf } from "../configure/vendors";
import { useMove } from "../numbers/parts";
import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { Field, Mark } from "../ui/setting";
import type { ProvidersRow } from "./settings-door";
import { Effect, Refusal, Section } from "./settings-parts";
import type { Known } from "./settings-stage";

interface VoiceRow {
  key: string;
  vendor: string;
  language: string;
  voice: string;
}

/** The rows of the `voices` map, `vendor/language` split, sorted by vendor then language. */
function voiceRows(voices: Readonly<Record<string, string>>): VoiceRow[] {
  return Object.entries(voices)
    .map(([key, voice]) => ({ key, vendor: key.slice(0, key.indexOf("/")), language: key.slice(key.indexOf("/") + 1), voice }))
    .sort((one, other) => one.vendor.localeCompare(other.vendor) || one.language.localeCompare(other.language));
}

/** `es` as `Spanish`; a code the browser does not know stays as typed. */
function languageSaid(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** `was` null is a new voice: its vendor and language are picked first. */
function VoicePanel({ was, tts, known, taken, saving, refused, onSave, onClose }: { was: VoiceRow | null; tts: string; known: Known; taken: readonly string[]; saving: boolean; refused: string | null; onSave: (key: string, voice: string) => void; onClose: () => void }): ReactNode {
  const [vendor, setVendor] = useState(was?.vendor ?? tts);
  const [language, setLanguage] = useState(was?.language ?? "");
  const [voice, setVoice] = useState(was?.voice ?? "");
  const [wrong, setWrong] = useState<string | null>(null);
  const speakers = (known.catalogue?.providers ?? []).filter((one) => one.does.includes("tts"));
  const lists = speakers.find((one) => one.name === vendor)?.voices_listed === true;
  const key = `${vendor}/${language}`;
  const save = (): void => {
    if (vendor === "" || language === "") return setWrong("Pick the vendor and type the language's code.");
    if (was === null && taken.includes(key)) return setWrong(`${brandOf(vendor)} already has a voice for ${languageSaid(language)}. Change that one.`);
    if (voice.trim() === "") return setWrong("Pick the voice.");
    setWrong(null);
    onSave(key, voice.trim());
  };
  return (
    <EditDialog title={was === null ? "Add a default voice" : `${brandOf(was.vendor)} in ${languageSaid(was.language)}`} icon="speaker" about="The voice an agent speaks with in this language when it has not chosen one." saving={saving} refused={wrong ?? refused} onSave={save} onClose={onClose}>
      <Effect>Every agent on this deployment that speaks this language through this vendor, and named no voice, sounds like this from its next call.</Effect>
      {was === null && (
        <>
          <Field label="Vendor">
            <Select items={speakers.map((one) => ({ value: one.name, label: brandOf(one.name), keywords: one.name, leading: <Mark letter={brandOf(one.name).charAt(0)} /> }))} value={vendor} label="Vendor" placeholder="Choose a vendor" onChange={(picked) => (setVendor(picked), setVoice(""))} />
          </Field>
          <Field label="Language">
            <input className="cfg-input" aria-label="Language" placeholder="Its code: es, en, pt…" spellCheck={false} value={language} onChange={(event) => setLanguage(event.target.value.trim().toLowerCase())} />
            {language !== "" && <p className="dash-quiet">{languageSaid(language)}</p>}
          </Field>
        </>
      )}
      {vendor !== "" && language !== "" && lists && <VoicePicker key={key} vendor={vendor} model="" language={language} voice={voice} onVoice={setVoice} />}
      {vendor !== "" && language !== "" && !lists && (
        <Field label="Voice id">
          <input className="cfg-input" aria-label="Voice id" placeholder={`As ${brandOf(vendor)} names it`} spellCheck={false} value={voice} onChange={(event) => setVoice(event.target.value)} />
        </Field>
      )}
    </EditDialog>
  );
}

export function DefaultVoices({ row, known, write }: { row: ProvidersRow; known: Known; write: (next: ProvidersRow) => Promise<void> }): ReactNode {
  const acting = useMove();
  // "" is a new voice, a key the one being changed.
  const [open, setOpen] = useState<string | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const rows = voiceRows(row.voices);
  const put = (key: string, voice: string | null): Promise<void> => {
    const voices = { ...row.voices };
    if (voice === null) delete voices[key];
    else voices[key] = voice;
    return acting.move(() => write({ ...row, voices }));
  };

  return (
    <>
      <Section
        icon="speaker"
        title="Voices by language"
        about="The voice a call speaks with when its agent names none. A language with no row uses the vendor's own voice."
        action={
          <button type="button" className="cfg-save tst-action" onClick={() => setOpen("")}>
            <Icon name="plus" size={12} />
            Add a voice
          </button>
        }
      >
        {open === null && <Refusal>{acting.refused}</Refusal>}
        {rows.length === 0 && <p className="dash-quiet tst-none">No language has a voice of its own yet.</p>}
        {rows.map((one) => (
          <div key={one.key} className="tst-row bxs-row">
            <Mark letter={brandOf(one.vendor).charAt(0)} />
            <span className="tst-row-words">
              <span className="tst-row-name">
                {languageSaid(one.language)}
                <span className="tst-tag">{brandOf(one.vendor)}</span>
              </span>
              <span className="tst-row-under bxs-code dash-clip">{one.voice}</span>
            </span>
            <span className="bxs-acts">
              <button type="button" className="app-button" onClick={() => setOpen(one.key)}>
                Change
              </button>
              <ConfirmButton label="Remove" asks="Back to the vendor's voice?" danger onConfirm={() => void put(one.key, null).catch(() => undefined)} />
            </span>
          </div>
        ))}
      </Section>
      {open !== null && (
        <VoicePanel
          key={open}
          was={rows.find((one) => one.key === open) ?? null}
          tts={row.defaults["tts"]?.vendor ?? ""}
          known={known}
          taken={Object.keys(row.voices)}
          saving={acting.busy}
          refused={acting.refused}
          onSave={(key, voice) => void put(key, voice).then(close, () => undefined)}
          onClose={close}
        />
      )}
    </>
  );
}
