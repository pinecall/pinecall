/** Whoami context: read once per key and shared with the tree. */

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { NoProduction } from "../screens/login/no-production";
import { useCredentials } from "@pinecall/core/credentials";
import { whoami, type Whose } from "@pinecall/core/whoami";
import { WORLD, type World } from "./mode";

export { orgOf, type Whose } from "@pinecall/core/whoami";

const Held = createContext<Whose | null>(null);

// Whoami succeeds for people without production access (`production: false`), but every other
// door would 403, so the production console stops with one message instead.
/** The refusal message for this key in production, or null when it may enter. */
export function keptOut(world: World, whose: Whose): string | null {
  if (world !== "production" || whose.production) return null;
  return `${whose.name ?? "This person"} has no production access: an admin gives it in Team.`;
}

export function WhoamiProvider({ children }: { children: ReactNode }): ReactNode {
  const credentials = useCredentials();
  const [whose, setWhose] = useState<Whose | null>(null);
  const [kept, setKept] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    setWhose(null);
    setKept(null);
    whoami(credentials).then(
      (answer) => {
        if (gone) return;
        const out = keptOut(WORLD, answer);
        if (out === null) setWhose(answer);
        else setKept(out);
      },
      // Older gateways refuse whoami itself with 403 in the same case.
      (failed: unknown) => {
        if (!gone && failed instanceof GatewayError && failed.status === 403) setKept(failed.message);
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  if (kept !== null) return <NoProduction said={kept} />;
  return <Held value={whose}>{children}</Held>;
}

/** The current identity, or null while loading. */
export function useWhoami(): Whose | null {
  return useContext(Held);
}

/** The key's scopes, or null while loading. */
export function useScopes(): readonly string[] | null {
  return useWhoami()?.scopes ?? null;
}
