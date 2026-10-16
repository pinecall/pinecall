/** Hook for the agents the gateway holds for the key's org and world. */

import { type HeldAgent } from "@pinecall/core/wire/rest-org";
import { useEffect, useState } from "react";

import { readHeldAgents } from "@pinecall/core/agents";
import { useCredentials } from "@pinecall/core/credentials";

export interface HeldAgents {
  agents: HeldAgent[];
  error: string | null;
  /** Whether the first read finished; distinguishes "loading" from "no agents". */
  loaded: boolean;
}

/** Read held agents; re-read when `tick` changes (the floor stream's agents-changed signal). */
export function useHeldAgents(tick = 0): HeldAgents {
  const credentials = useCredentials();
  const [agents, setAgents] = useState<HeldAgent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let stopped = false;
    void (async () => {
      try {
        const held = await readHeldAgents(credentials);
        if (!stopped) {
          setAgents(held);
          setError(null);
        }
      } catch (refused) {
        if (!stopped) setError(String(refused));
      } finally {
        if (!stopped) setLoaded(true);
      }
    })();
    return () => {
      stopped = true;
    };
  }, [credentials, tick]);

  return { agents, error, loaded };
}
