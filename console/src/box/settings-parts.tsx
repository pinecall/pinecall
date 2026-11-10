/** What Box settings' tabs share: a door read once and re-read, a section with its head, the note of what a write does, and a refusal. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { Icon, type IconName } from "../shell/icons";

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
      (answered) => !gone && setValue(answered),
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [ask]);

  return { value, refused, reread };
}

/** A section: a neutral icon tile, its name with one line under it, what it does at the right, then its rows. */
export function Section({ icon, title, about, action, children }: { icon: IconName; title: string; about: ReactNode; action?: ReactNode; children: ReactNode }): ReactNode {
  return (
    <section className="tst-list" aria-label={title}>
      <header className="tst-head">
        <span className="tst-head-mark" aria-hidden="true">
          <Icon name={icon} size={16} />
        </span>
        <span className="tst-head-words">
          <span className="tst-head-title">{title}</span>
          <span className="tst-head-about">{about}</span>
        </span>
        {action}
      </header>
      {children}
    </section>
  );
}

/** In a panel, before its fields: what saving does to the organizations on this deployment. */
export function Effect({ children }: { children: ReactNode }): ReactNode {
  return (
    <p className="bxs-effect">
      <b>What this does</b>
      {children}
    </p>
  );
}

/** The gateway's own sentence, when a read or a write failed. */
export function Refusal({ children }: { children: string | null | undefined }): ReactNode {
  if (children === null || children === undefined) return null;
  return (
    <p className="cfg-refused" role="alert">
      {children}
    </p>
  );
}

/** What a tab says for a door this gateway version does not have. */
export function NoSuchDoor(): ReactNode {
  return <p className="dash-quiet tst-none">This version of the runtime does not have this setting yet.</p>;
}
