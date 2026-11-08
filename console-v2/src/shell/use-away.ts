/** A menu's way of closing: a press outside what the ref holds, or Escape. */

import { useEffect, useRef, type RefObject } from "react";

export function useAway(open: boolean, close: () => void): RefObject<HTMLDivElement | null> {
  const held = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent): void => {
      if (!held.current?.contains(event.target as Node)) close();
    };
    const escaped = (event: KeyboardEvent): void => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escaped);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escaped);
    };
  }, [open, close]);
  return held;
}
