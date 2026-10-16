/** Hooks to read a gateway door on mount (with reload) and to run one write at a time. */

import { useCallback, useEffect, useState } from "react";

import { GatewayError } from "@pinecall/core/api";

export interface Door<T> {
  /** Undefined until the door has answered. */
  value: T | undefined;
  refused: string | null;
  reread: () => Promise<void>;
}

/** `ask` must be stable (a useCallback): it is what the read is keyed on. */
export function useDoor<T>(ask: () => Promise<T>): Door<T> {
  const [value, setValue] = useState<T | undefined>(undefined);
  const [refused, setRefused] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => {
    try {
      setValue(await ask());
      setRefused(null);
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  }, [ask]);

  useEffect(() => {
    let gone = false;
    ask().then(
      (answered) => {
        if (!gone) setValue(answered);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [ask]);

  return { value, refused, reread };
}

/** The gateway's refusal message, verbatim. */
export function saidBy(failed: unknown): string {
  return failed instanceof GatewayError ? failed.message : failed instanceof Error ? failed.message : String(failed);
}

/** Run one write at a time, tracking busy state and the gateway's refusal. */
export function useMove(): { busy: boolean; refused: string | null; move: (what: () => Promise<void>) => Promise<boolean> } {
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const move = useCallback(async (what: () => Promise<void>): Promise<boolean> => {
    setBusy(true);
    setRefused(null);
    try {
      await what();
      return true;
    } catch (failed) {
      setRefused(saidBy(failed));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, refused, move };
}
