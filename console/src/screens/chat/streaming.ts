/** Streaming agent replies: accumulate log deltas and reveal them per animation frame. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { useEffect, useRef, useState } from "react";

/**
 * Accumulated reply text by speech id. Each `agent.transcript` is a delta; the reducer only joins
 * the in-flight reply, but the chat needs every reply. Once `turn.agent` lands, its text wins.
 */
export function repliesOf(entries: Entry[]): { streaming: Map<string, string>; settled: Set<string> } {
  const streaming = new Map<string, string>();
  const settled = new Set<string>();
  for (const entry of entries) {
    if (entry.type === "agent.transcript") {
      const data = entry.data as { speech_id: string; text: string; final: boolean };
      if (data.final) continue;
      streaming.set(data.speech_id, (streaming.get(data.speech_id) ?? "") + data.text);
    } else if (entry.type === "turn.agent") {
      settled.add((entry.data as { speech_id: string }).speech_id);
    }
  }
  return { streaming, settled };
}

// Reveal progress per reply, shared across mounts so the settled bubble continues where the
// streaming one stopped.
const revealed = new Map<string, number>();

// Per frame: at least MIN chars plus SHARE of the hidden remainder, so bursts catch up quickly.
const MIN_PER_FRAME = 1;
const SHARE_PER_FRAME = 0.18;

/** Text to show this frame; grows toward `target` and never shrinks. `instant` skips the animation. */
export function useRevealed(key: string, target: string, instant: boolean): string {
  const [shown, setShown] = useState(() => (instant ? target.length : (revealed.get(key) ?? 0)));
  const aim = useRef(target.length);
  aim.current = target.length;

  useEffect(() => {
    if (instant) {
      revealed.set(key, target.length);
      setShown(target.length);
      return;
    }
    let frame = 0;
    const step = (): void => {
      setShown((now) => {
        const left = aim.current - now;
        if (left <= 0) return now;
        const next = Math.min(aim.current, now + Math.max(MIN_PER_FRAME, Math.ceil(left * SHARE_PER_FRAME)));
        revealed.set(key, next);
        return next;
      });
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [key, instant, target.length]);

  return target.slice(0, Math.min(shown, target.length));
}
