/** The voice a call speaks with when nobody chose one, per vendor and language, each picked by ear. */

import { useState, type ReactNode } from "react";

import { VoicePicker } from "../settings";
import { Button, Card, CardHead, Input, TextAction } from "../../ui";

/** The rows of the `voices` map, `vendor/language` split, sorted by vendor then language. */
export function voiceRows(voices: Record<string, string>): { vendor: string; language: string; voice: string }[] {
  return Object.entries(voices)
    .map(([key, voice]) => {
      const at = key.indexOf("/");
      return { vendor: key.slice(0, at), language: key.slice(at + 1), voice };
    })
    .sort((one, other) => one.vendor.localeCompare(other.vendor) || one.language.localeCompare(other.language));
}

const LINE = { es: "Hola, ¿en qué te puedo ayudar?", en: "Hi, how can I help you?", pt: "Olá, como posso ajudar?" } as Record<string, string>;

export function DefaultVoices({
  voices,
  tts,
  onChange,
}: {
  voices: Record<string, string>;
  /** The default voice vendor, the one a new row is for. */
  tts: string;
  onChange: (voices: Record<string, string>) => void;
}): ReactNode {
  const [open, setOpen] = useState<string | null>(null);
  const [language, setLanguage] = useState("");
  const rows = voiceRows(voices);

  const put = (key: string, voice: string | null): void => {
    const next = { ...voices };
    if (voice === null) delete next[key];
    else next[key] = voice;
    onChange(next);
  };

  return (
    <Card>
      <CardHead title="Voices by language" meta="the voice a call speaks with when the agent names none" />
      <div className="box-body">
        {rows.length === 0 && <span className="ui-note">No language has a voice of its own: a call speaks with the vendor's default voice. Add one below.</span>}
        {rows.map((row) => {
          const key = `${row.vendor}/${row.language}`;
          return (
            <div key={key} className="box-voice">
              <div className="box-voice-line">
                <span className="box-mono">{key}</span>
                <span className="box-fixed">{row.voice}</span>
                <TextAction onClick={() => setOpen(open === key ? null : key)}>{open === key ? "Done" : "Choose by ear"}</TextAction>
                <TextAction danger onClick={() => put(key, null)}>
                  Remove
                </TextAction>
              </div>
              {open === key && (
                <VoicePicker vendor={row.vendor} model={null} language={row.language} opening={LINE[row.language] ?? LINE["en"] ?? ""} voice={row.voice} onChange={(voice) => put(key, voice)} />
              )}
            </div>
          );
        })}
        <div className="box-line">
          <span className="box-add-input">
            <Input value={language} placeholder="a language: es, en, pt…" onChange={(event) => setLanguage(event.target.value.trim().toLowerCase())} />
          </span>
          <Button
            size="md"
            disabled={language === "" || `${tts}/${language}` in voices}
            onClick={() => {
              put(`${tts}/${language}`, "");
              setOpen(`${tts}/${language}`);
              setLanguage("");
            }}
          >
            Add a voice for {tts}
          </Button>
        </div>
      </div>
    </Card>
  );
}
