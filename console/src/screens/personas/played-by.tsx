/** How a persona is played: the model that improvises them and the voice their lines are read in, picked from what this box runs. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { doing, readCatalogue, type Catalogue, type Modality } from "../../lib/catalogue";
import { Input, Label, Select, SelectItem } from "../../ui";
import { VoiceField } from "../settings/stages";
import "../settings/settings.css";

/** The three words a persona is played by; "" is the runtime's choice. */
export interface Played {
  llm: string;
  tts: string;
  voice: string;
}

/** `vendor/model` as its two halves; a vendor alone has no model. */
function halves(word: string): [string, string] {
  const at = word.indexOf("/");
  return at < 0 ? [word, ""] : [word.slice(0, at), word.slice(at + 1)];
}

export function PlayedBy({ played, onChange }: { played: Played; onChange: (played: Played) => void }): ReactNode {
  const credentials = useCredentials();
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    readCatalogue(credentials).then(
      (read) => live && setCatalogue(read),
      (failed: unknown) => live && setRefused(saidBy(failed)),
    );
    return () => {
      live = false;
    };
  }, [credentials]);

  if (catalogue === null) return <p className="set-help">{refused ?? "Asking the gateway what this box runs…"}</p>;
  const [vendor, model] = halves(played.llm);
  const [speaker] = halves(played.tts);
  // Only what this box runs, plus what is written already, said so, rather than a list that
  // quietly reads as "the runtime's choice".
  const vendors = (modality: Modality, written: string): string[] => {
    const ready = doing(catalogue.providers, modality).filter((one) => one.ready).map((one) => one.name);
    return written === "" || ready.includes(written) ? ready : [written, ...ready];
  };
  const known = catalogue.models[`llm/${vendor}`]?.[0];
  return (
    <div className="psn-played">
      <div className="set-row">
        <div className="set-field">
          <Label>Model vendor</Label>
          <Select value={vendor} aria-label="Model vendor" onValueChange={(value) => onChange({ ...played, llm: value })}>
            <SelectItem value="">The callers' model, the box's</SelectItem>
            {vendors("llm", vendor).map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </Select>
        </div>
        {vendor !== "" && (
          <div className="set-field">
            <Label>Model</Label>
            <Input
              value={model}
              spellCheck={false}
              aria-label="Model"
              placeholder={known === undefined ? `${vendor}'s default` : `${vendor}'s default · ${known}`}
              onChange={(event) => onChange({ ...played, llm: event.target.value.trim() === "" ? vendor : `${vendor}/${event.target.value.trim()}` })}
            />
          </div>
        )}
      </div>
      <div className="set-row">
        <div className="set-field">
          <Label>Voice vendor</Label>
          <Select value={speaker} aria-label="Voice vendor" onValueChange={(value) => onChange({ ...played, tts: value, voice: "" })}>
            <SelectItem value="">The runtime's: a voice the agent does not have</SelectItem>
            {vendors("tts", speaker).map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </Select>
        </div>
      </div>
      {speaker !== "" && (
        <VoiceField vendor={speaker} providers={catalogue.providers} model={null} language={null} opening="" voice={played.voice} onChange={(voice) => onChange({ ...played, voice })} />
      )}
    </div>
  );
}
