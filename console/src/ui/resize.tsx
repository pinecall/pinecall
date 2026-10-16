/** A pane a person drags wider or narrower, and finds as they left it. */

import { useCallback, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";

import { forgetWidth, keepWidth, keptWidth } from "../lib/preferences";

/** A pane's width, where it may go, and which of its edges is dragged. */
export interface Pane {
  width: number;
  /** Set on the grid that holds the pane: its columns read `var(--pane)`. */
  style: CSSProperties;
  handle: ReactNode;
}

interface Wanted {
  /** The name the width is kept under: one per pane, so one screen's is not another's. */
  name: string;
  initial: number;
  min: number;
  max: number;
  /** Which side of the screen the pane is on: a pane on the right grows as the pointer goes left. */
  side: "left" | "right";
}

const clamped = (width: number, min: number, max: number): number => Math.min(max, Math.max(min, width));

/** The width of one pane, dragged by its handle and kept by the browser. Double-click resets it. */
export function usePane({ name, initial, min, max, side }: Wanted): Pane {
  const [width, setWidth] = useState(() => clamped(keptWidth(name) ?? initial, min, max));
  const from = useRef<{ x: number; width: number } | null>(null);

  const down = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      from.current = { x: event.clientX, width };
    },
    [width],
  );

  const move = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (from.current === null) return;
      const moved = event.clientX - from.current.x;
      setWidth(clamped(from.current.width + (side === "right" ? -moved : moved), min, max));
    },
    [side, min, max],
  );

  const up = useCallback(() => {
    if (from.current === null) return;
    from.current = null;
    keepWidth(name, width);
  }, [name, width]);

  const reset = useCallback(() => {
    forgetWidth(name);
    setWidth(initial);
  }, [name, initial]);

  return {
    width,
    style: { "--pane": `${String(width)}px` } as CSSProperties,
    handle: (
      <div
        className={side === "right" ? "ui-resize ui-resize-right" : "ui-resize ui-resize-left"}
        role="separator"
        aria-orientation="vertical"
        aria-label="Drag to resize. Double-click to reset."
        title="Drag to resize · double-click to reset"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onDoubleClick={reset}
      />
    ),
  };
}
