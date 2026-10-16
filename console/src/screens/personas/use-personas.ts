/** Hook for one agent's personas, or — "" — every agent's, or — null — none asked for; loaded once per agent and read again on asking. */

import { useCallback, useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readEveryPersona, readPersonas, type Persona } from "./door";

export function usePersonas(agent: string | null): {
  personas: Persona[] | null;
  asking: string | null;
  setPersonas: (personas: Persona[]) => void;
  reread: () => void;
} {
  const credentials = useCredentials();
  const [personas, setPersonas] = useState<Persona[] | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  const [round, setRound] = useState(0);

  useEffect(() => {
    if (agent === null) {
      setPersonas(null);
      setAsking(null);
      return;
    }
    let gone = false;
    setAsking("Asking the gateway…");
    (agent === "" ? readEveryPersona(credentials) : readPersonas(credentials, agent)).then(
      (read) => {
        if (gone) return;
        setPersonas(read);
        setAsking(null);
      },
      (failed: unknown) => {
        if (!gone) setAsking(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent, round]);

  const reread = useCallback(() => setRound((one) => one + 1), []);
  return { personas, asking, setPersonas, reread };
}
