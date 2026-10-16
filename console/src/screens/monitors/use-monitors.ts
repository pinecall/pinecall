/** Hook for the world's monitors: read once, kept as adds and drops answer. */

import { useEffect, useState } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { readMonitors, type Monitor } from "./door";

export interface Monitors {
  monitors: Monitor[] | null;
  /** Why the gateway would not answer, while it would not. */
  asking: string | null;
  setMonitors: (monitors: Monitor[]) => void;
}

export function useMonitors(): Monitors {
  const credentials = useCredentials();
  const [monitors, setMonitors] = useState<Monitor[] | null>(null);
  const [asking, setAsking] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setMonitors(null);
    readMonitors(credentials)
      .then((read) => live && (setMonitors(read), setAsking(null)))
      .catch((failed: unknown) => live && setAsking(saidBy(failed)));
    return () => {
      live = false;
    };
  }, [credentials]);

  return { monitors, asking, setMonitors };
}
