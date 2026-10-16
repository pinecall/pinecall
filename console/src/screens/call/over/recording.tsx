/** Call recording player: fetches audio with the key and plays it from a blob URL. */

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { doorUrl, headersFor } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";

// The pointer is only in call.summary (worker/recordings.py). <audio src> can't send headers and
// the key never goes in a URL, so fetch with the key and play an object URL, revoked on unmount.
/** The recording path from call.summary, or null when nothing was recorded. */
export function recordingIn(summary: Record<string, unknown> | undefined): string | null {
  const path = summary?.["recording"];
  return typeof path === "string" && path !== "" ? path : null;
}

export function Player({ call, onNothing }: { call: string; onNothing?: () => void }): ReactNode {
  const credentials = useCredentials();
  const [src, setSrc] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  // try/catch, not `.then(ok, err)`: a throw inside `ok` never reaches `err`.
  useEffect(() => {
    let url: string | null = null;
    let gone = false;
    void (async () => {
      try {
        const answer = await fetch(doorUrl(credentials, `/v1/calls/${call}/recording`), {
          headers: headersFor(credentials),
        });
        // 404 means no audio. With `onNothing`, the caller hides the card instead of showing a message.
        if (answer.status === 404 && onNothing !== undefined) {
          if (!gone) onNothing();
          return;
        }
        if (!answer.ok) throw new Error(await whyNot(answer));
        url = URL.createObjectURL(await answer.blob());
        if (gone) URL.revokeObjectURL(url);
        else setSrc(url);
      } catch (failed) {
        if (!gone) setRefused(failed instanceof Error ? failed.message : String(failed));
      }
    })();
    return () => {
      gone = true;
      if (url !== null) URL.revokeObjectURL(url);
    };
  }, [call, credentials, onNothing]);

  if (refused !== null) return <p className="over-tape-note">{refused}</p>;
  if (src === null) return <p className="over-tape-note">Reading the recording…</p>;
  return <Tape src={src} />;
}

// Custom controls (play, position, seek bar) because native ones render differently per browser.
function Tape({ src }: { src: string }): ReactNode {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [at, setAt] = useState(0);
  const [length, setLength] = useState(0);

  const toggle = (): void => {
    const player = audio.current;
    if (player === null) return;
    if (player.paused) void player.play();
    else player.pause();
  };

  return (
    <div className="over-tape">
      <audio
        ref={audio}
        src={src}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(event) => setAt(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => setLength(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0)}
      />
      <button type="button" className="over-tape-play" onClick={toggle} aria-label={playing ? "Pause the recording" : "Play the recording"}>
        {playing ? "❚❚" : "▶"}
      </button>
      <span className="over-tape-time">{clock(at)}</span>
      <input
        className="over-tape-bar"
        type="range"
        min={0}
        max={length || 1}
        step={0.1}
        value={at}
        aria-label="Where in the recording"
        style={{ "--played": `${length > 0 ? (at / length) * 100 : 0}%` } as CSSProperties}
        onChange={(event) => {
          const player = audio.current;
          if (player !== null) player.currentTime = Number(event.target.value);
        }}
      />
      <span className="over-tape-time">{clock(length)}</span>
    </div>
  );
}

function clock(seconds: number): string {
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// Prefer the gateway's message (it says where the file is); fall back to the status.
async function whyNot(answer: Response): Promise<string> {
  try {
    const said: unknown = await answer.json();
    const detail = (said as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  } catch {
    // A proxy may answer with non-JSON.
  }
  return `the recording answered ${answer.status}`;
}
