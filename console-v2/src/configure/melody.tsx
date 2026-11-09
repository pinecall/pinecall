/** The hold melody on Configure: what a caller hears while a tool runs, listened to, replaced by a file or turned off, saved as it is chosen. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Setting, Slider } from "../ui/setting";
import { chooseHold, holdBlob, readHold, setHoldAfter, uploadHold, type Hold } from "./hold-door";
import { Locked } from "./stages";
import "./melody.css";

// A slider moved is one write once it rests.
const WAIT_SAVES_AFTER_MS = 600;

function nowPlaying(hold: Hold): string {
  if (hold.played === "off") return "Off: silence while a tool runs.";
  const after = `after ${hold.after_s} s of quiet`;
  return hold.played === "default" ? `The runtime's own melody, ${after}.` : `${hold.name ?? "Your file"}, ${after}.`;
}

export function Melody({ agent, readOnly }: { agent: string; readOnly: boolean }): ReactNode {
  const credentials = useCredentials();
  const [hold, setHold] = useState<Hold | null>(null);
  const [wait, setWait] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const took = (read: Hold): void => {
    setHold(read);
    setWait(String(read.after_s));
    setPlaying(null);
  };

  useEffect(() => {
    let gone = false;
    readHold(credentials, agent).then((read) => !gone && took(read), (failed: unknown) => !gone && setRefused(saidBy(failed)));
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  useEffect(
    () => () => {
      if (playing !== null) URL.revokeObjectURL(playing);
    },
    [playing],
  );

  useEffect(() => {
    if (hold === null || wait === "" || Number(wait) === hold.after_s) return undefined;
    const waiting = window.setTimeout(() => {
      setHoldAfter(credentials, agent, Number(wait)).then(() => setHold({ ...hold, after_s: Number(wait) }), (failed: unknown) => setRefused(saidBy(failed)));
    }, WAIT_SAVES_AFTER_MS);
    return () => window.clearTimeout(waiting);
  }, [credentials, agent, hold, wait]);

  const act = async (doing: string, move: () => Promise<Hold>): Promise<void> => {
    setBusy(doing);
    setRefused(null);
    try {
      took(await move());
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(null);
    }
  };

  const listen = async (): Promise<void> => {
    setRefused(null);
    try {
      setPlaying(await holdBlob(credentials, agent));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const chosen = (file: File | undefined): void => {
    if (file !== undefined) void act("Converting…", () => uploadHold(credentials, agent, file));
    if (picker.current !== null) picker.current.value = "";
  };

  const canChange = hold !== null && !hold.fixed && !readOnly;
  const actions = (
    <div className="cfg-melody-actions">
      {hold !== null && hold.played !== "off" && (
        <button type="button" className="app-button" onClick={() => void listen()}>
          Listen
        </button>
      )}
      {canChange && (
        <button type="button" className="app-button" disabled={busy !== null} onClick={() => picker.current?.click()}>
          {busy ?? "Upload a file"}
        </button>
      )}
      {canChange && hold.played !== "default" && (
        <button type="button" className="app-button" disabled={busy !== null} onClick={() => void act("Saving…", () => chooseHold(credentials, agent, "default"))}>
          Use the default
        </button>
      )}
      {canChange && hold.played !== "off" && (
        <button type="button" className="app-button" disabled={busy !== null} onClick={() => void act("Saving…", () => chooseHold(credentials, agent, "off"))}>
          Turn off
        </button>
      )}
      {hold?.fixed === true && <Locked />}
    </div>
  );

  return (
    <section className="dash-card cfg-melody" aria-label="Hold melody">
      <Setting icon="speaker" title="Hold melody" about={hold === null ? "Reading what it plays…" : nowPlaying(hold)} aside={actions}>
        {hold !== null && hold.played !== "off" && <Slider value={wait} label="Seconds of quiet before the melody starts" min={0} max={30} step={0.5} rest={2.5} ends={["At once", "30 s"]} disabled={!canChange} onChange={setWait} />}
        {playing !== null && <audio className="cfg-melody-player" controls autoPlay src={playing} />}
        {canChange && <p className="dash-quiet">A wav, an mp3, an ogg or an m4a, up to 20 MB and five minutes. Phone and web alike, from the next call.</p>}
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}
      </Setting>
      <input ref={picker} type="file" accept="audio/*,.mp3,.wav,.ogg,.m4a" hidden aria-label="Melody file" onChange={(event) => chosen(event.target.files?.[0])} />
    </section>
  );
}
