/** A sentence heard in a vendor's voice, one at a time: the hook that plays a sample, and the round button that asks for it. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { sampleOf } from "./door";

type Asked = Parameters<typeof sampleOf>[1];

/** Plays one sample at a time; `playing` is the id it was asked under, and `stop` silences it. */
export function useListen(): { playing: string | null; refused: string | null; listen: (id: string, asked: Asked) => Promise<void>; stop: () => void } {
  const credentials = useCredentials();
  const [playing, setPlaying] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const stop = (): void => audio.current?.pause();
  useEffect(() => () => audio.current?.pause(), []);

  const listen = async (id: string, asked: Asked): Promise<void> => {
    stop();
    setPlaying(id);
    setRefused(null);
    try {
      const url = await sampleOf(credentials, asked);
      const player = new Audio(url);
      audio.current = player;
      player.onended = () => {
        URL.revokeObjectURL(url);
        setPlaying(null);
      };
      await player.play();
    } catch (failed) {
      setPlaying(null);
      setRefused(saidBy(failed));
    }
  };
  return { playing, refused, listen, stop };
}

export function ListenButton({ playing, label, disabled = false, onClick }: { playing: boolean; label: string; disabled?: boolean; onClick: () => void }): ReactNode {
  return (
    <button type="button" className={playing ? "pick-play pick-playing" : "pick-play"} aria-label={label} title={label} disabled={disabled} onClick={onClick}>
      <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        {playing ? <path d="M6 5h4v14H6zM14 5h4v14h-4z" /> : <path d="M7 4v16l13-8z" />}
      </svg>
    </button>
  );
}
