/** Hold audio card: default melody, none, or an uploaded file. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead } from "../../ui";
import { chooseHoldAudio, holdAudioBlob, readHoldAudio, uploadHoldAudio, type HoldAudio } from "./door";

// Saved immediately on choice, not with the settings Save button.
export function HoldMelody({ agent }: { agent: string }): ReactNode {
  const credentials = useCredentials();
  const [held, setHeld] = useState<HoldAudio | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let gone = false;
    readHoldAudio(credentials, agent).then(
      (said) => !gone && setHeld(said),
      (failed: unknown) => !gone && setError(failed instanceof Error ? failed.message : String(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  // Revoke the old blob URL.
  useEffect(() => () => {
    if (src !== null) URL.revokeObjectURL(src);
  }, [src]);

  const act = async (doing: string, move: () => Promise<HoldAudio>): Promise<void> => {
    setBusy(doing);
    setError(null);
    try {
      setHeld(await move());
      setSrc(null);
    } catch (failed) {
      setError(failed instanceof Error ? failed.message : String(failed));
    } finally {
      setBusy(null);
    }
  };

  const listen = async (): Promise<void> => {
    setError(null);
    try {
      setSrc(await holdAudioBlob(credentials, agent));
    } catch (failed) {
      setError(failed instanceof Error ? failed.message : String(failed));
    }
  };

  const chosen = (file: File | undefined): void => {
    if (file === undefined) return;
    void act("Converting…", () => uploadHoldAudio(credentials, agent, file));
    if (picker.current !== null) picker.current.value = "";
  };

  return (
    <Card>
      <CardHead title="Hold melody" meta="what the caller hears while a tool runs — phone and web alike, from the next call" />
      <div className="pipe-hold">
        <div className="pipe-hold-now">
          <b>{held === null ? "…" : held.played === "off" ? "Off" : (held.name ?? "Your file")}</b>
          <span className="pipe-note">
            {held === null
              ? "Asking the gateway."
              : held.played === "off"
                ? "Silence while a tool runs."
                : `${held.played === "default" ? "The runtime's own" : "Uploaded"} · ${held.seconds ?? "?"} s, looped under the wait at 60 %, after 0.6 s.`}
          </span>
        </div>
        <div className="pipe-hold-actions">
          {held !== null && held.played !== "off" && (
            <Button size="sm" onClick={() => void listen()} disabled={busy !== null}>
              Listen
            </Button>
          )}
          <Button size="sm" onClick={() => picker.current?.click()} disabled={busy !== null}>
            {busy ?? "Upload a file…"}
          </Button>
          {held !== null && held.played !== "default" && (
            <Button size="sm" onClick={() => void act("Saving…", () => chooseHoldAudio(credentials, agent, "default"))} disabled={busy !== null}>
              Use the default
            </Button>
          )}
          {held !== null && held.played !== "off" && (
            <Button size="sm" onClick={() => void act("Saving…", () => chooseHoldAudio(credentials, agent, "off"))} disabled={busy !== null}>
              Turn off
            </Button>
          )}
          <input
            ref={picker}
            type="file"
            accept="audio/*,.mp3,.wav,.ogg,.m4a"
            hidden
            onChange={(event) => chosen(event.target.files?.[0])}
          />
        </div>
        {src !== null && <audio className="pipe-hold-player" controls autoPlay src={src} />}
        {error !== null ? (
          <span className="pipe-save-error">{error}</span>
        ) : (
          <span className="pipe-save-note">A wav, an mp3, an ogg or an m4a, up to 20 MB and five minutes: the gateway converts it.</span>
        )}
      </div>
    </Card>
  );
}
