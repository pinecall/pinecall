/** A button for what is hard to undo: the first click asks, the second does it, and it forgets after a moment. */

import { useEffect, useState, type ReactNode } from "react";

const FORGETS_MS = 4000;

export function ConfirmButton({ label, asks, danger = false, onConfirm }: { label: string; asks: string; danger?: boolean; onConfirm: () => void }): ReactNode {
  const [asking, setAsking] = useState(false);
  useEffect(() => {
    if (!asking) return;
    const timer = window.setTimeout(() => setAsking(false), FORGETS_MS);
    return () => window.clearTimeout(timer);
  }, [asking]);
  return (
    <button
      type="button"
      className={`app-button${danger ? " app-button-danger" : ""}${asking ? " app-button-asking" : ""}`}
      onClick={() => {
        if (!asking) return setAsking(true);
        setAsking(false);
        onConfirm();
      }}
    >
      {asking ? asks : label}
    </button>
  );
}
