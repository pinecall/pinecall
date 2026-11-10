/** The call's audio, pinned under the conversation: fetched with the key, played from a blob, and sought by the times in the chat. */

import { useEffect, useImperativeHandle, useRef, useState, type ReactNode, type RefObject } from "react";

import { doorUrl, headersFor } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Icon } from "../shell/icons";

/** What the page can ask of the tape. */
export interface TapeControl {
  /** Go to a moment of the recording, in seconds, and play from there. */
  seek: (at: number) => void;
}

function clock(seconds: number): string {
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// The gateway's message says where the file is; a proxy may answer with no JSON at all.
async function whyNot(answer: Response): Promise<string> {
  try {
    const said: unknown = await answer.json();
    const detail = (said as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  } catch {
    // Not JSON.
  }
  return `The recording answered ${answer.status}.`;
}

function Tape({ src, control, onReady }: { src: string; control: RefObject<TapeControl | null>; onReady: (ready: boolean) => void }): ReactNode {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [at, setAt] = useState(0);
  const [length, setLength] = useState(0);

  useImperativeHandle(
    control,
    () => ({
      seek: (moment) => {
        const player = audio.current;
        if (player === null) return;
        player.currentTime = moment;
        void player.play();
      },
    }),
    [],
  );

  useEffect(() => {
    onReady(true);
    return () => onReady(false);
  }, [onReady]);

  const toggle = (): void => {
    const player = audio.current;
    if (player === null) return;
    if (player.paused) void player.play();
    else player.pause();
  };

  return (
    <div className="calls-tape">
      <audio ref={audio} src={src} preload="metadata" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onTimeUpdate={(event) => setAt(event.currentTarget.currentTime)} onLoadedMetadata={(event) => setLength(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0)} />
      <button type="button" className="calls-tape-play" onClick={toggle} aria-label={playing ? "Pause the recording" : "Play the recording"}>
        <Icon name={playing ? "pause" : "play"} size={13} />
      </button>
      <span className="calls-tape-time">{clock(at)}</span>
      <input
        className="calls-tape-bar"
        type="range"
        min={0}
        max={length || 1}
        step={0.1}
        value={at}
        aria-label="Where in the recording"
        onChange={(event) => {
          const player = audio.current;
          if (player !== null) player.currentTime = Number(event.target.value);
        }}
      />
      <span className="calls-tape-time">{clock(length)}</span>
    </div>
  );
}

// <audio src> cannot send headers and the key never goes in a URL: the file is fetched with the key and played from an object URL.
export function Recording({ call, control, onReady }: { call: string; control: RefObject<TapeControl | null>; onReady: (ready: boolean) => void }): ReactNode {
  const credentials = useCredentials();
  const [src, setSrc] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [nothing, setNothing] = useState(false);

  useEffect(() => {
    let url: string | null = null;
    let gone = false;
    void (async () => {
      try {
        const answer = await fetch(doorUrl(credentials, `/v1/calls/${call}/recording`), { headers: headersFor(credentials) });
        if (answer.status === 404) {
          if (!gone) setNothing(true);
          return;
        }
        if (!answer.ok) throw new Error(await whyNot(answer));
        url = URL.createObjectURL(await answer.blob());
        if (gone) URL.revokeObjectURL(url);
        else setSrc(url);
      } catch (failed) {
        if (!gone) setSaid(failed instanceof Error ? failed.message : String(failed));
      }
    })();
    return () => {
      gone = true;
      if (url !== null) URL.revokeObjectURL(url);
    };
  }, [call, credentials]);

  if (nothing) return null;
  if (src !== null) return <Tape src={src} control={control} onReady={onReady} />;
  return <p className="dash-quiet calls-tape calls-tape-note">{said ?? "Reading the recording…"}</p>;
}
