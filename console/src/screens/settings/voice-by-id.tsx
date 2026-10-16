/** A voice named by its id, for any vendor: heard first, then used — the voices no list carries. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Input, Label } from "../../ui";
import { heard } from "./voice-doors";

/** Whether `Use` may take the id typed: only one the vendor has just said a line with. */
export function usable(typed: string, heardWith: string | null, inUse: string): boolean {
  const id = typed.trim();
  return id !== "" && id === heardWith && id !== inUse;
}

// The sample is the proof: a vendor that has no such voice refuses it here, in its own words,
// instead of on the next call. It goes through the path a call speaks on, so any vendor works.
export function VoiceById({
  vendor,
  model,
  language,
  opening,
  voice,
  onChange,
  label,
}: {
  vendor: string;
  model: string | null;
  language: string | null;
  /** The agent's own opening, which the voice says when there is one. */
  opening: string;
  voice: string;
  onChange: (voice: string) => void;
  label: string;
}): ReactNode {
  const credentials = useCredentials();
  const [typed, setTyped] = useState("");
  const [asking, setAsking] = useState(false);
  const [heardWith, setHeardWith] = useState<string | null>(null);
  const [wait, setWait] = useState<number | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const sample = useRef<string | null>(null);

  // A blob URL is memory until it is revoked: the last one goes with the field.
  useEffect(
    () => () => {
      player.current?.pause();
      if (sample.current !== null) URL.revokeObjectURL(sample.current);
    },
    [],
  );

  const listen = async (): Promise<void> => {
    const id = typed.trim();
    player.current?.pause();
    if (sample.current !== null) URL.revokeObjectURL(sample.current);
    sample.current = null;
    setAsking(true);
    setRefused(null);
    try {
      const said = opening.trim();
      const answer = await heard(credentials, { tts: vendor, voice: id, model, language, ...(said === "" ? {} : { text: said }) });
      sample.current = answer.url;
      setHeardWith(id);
      setWait(answer.firstAudioMs);
      player.current = new Audio(answer.url);
      await player.current.play();
    } catch (failed) {
      setHeardWith(null);
      setRefused(saidBy(failed));
    } finally {
      setAsking(false);
    }
  };

  const id = typed.trim();
  return (
    <div className="set-voices-line">
      <Label>{label}</Label>
      <div className="set-voices-by-id">
        <Input
          value={typed}
          placeholder={`The id ${vendor} gives the voice`}
          aria-label="Voice id"
          onChange={(event) => {
            setTyped(event.target.value);
            setRefused(null);
          }}
        />
        <Button size="xs" disabled={id === "" || asking} onClick={() => void listen()}>
          {asking ? "…" : "Listen"}
        </Button>
        <Button size="xs" kind="primary" disabled={!usable(typed, heardWith, voice)} onClick={() => onChange(id)}>
          Use
        </Button>
      </div>
      {refused !== null && <p className="set-help set-voices-refused">{refused}</p>}
      {refused === null && heardWith === id && id !== "" && (
        <p className="set-help">{wait === null ? `${vendor} said it.` : `${vendor} said it: ${wait} ms to the first audio.`} Use it, then save.</p>
      )}
    </div>
  );
}
