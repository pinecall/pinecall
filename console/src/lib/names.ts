/** The org's people by name, read once for a key that may read them: who set a monitor, who read a call, who asked for an erasure. */

import { useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readMembers } from "@pinecall/core/members";
import { useScopes } from "./whoami";

/**
 * A member's name by id — empty until read, and for a key without `team`. Names are a courtesy:
 * a screen that cannot have them says the id, never refuses for them.
 */
export function useNames(): ReadonlyMap<string, string> {
  const credentials = useCredentials();
  const scopes = useScopes();
  const [names, setNames] = useState<ReadonlyMap<string, string>>(new Map());
  const mayRead = scopes !== null && scopes.includes("team");

  useEffect(() => {
    if (!mayRead) return;
    let gone = false;
    readMembers(credentials)
      .then((members) => {
        if (!gone) setNames(new Map(members.map((one) => [one.id, one.name || one.email])));
      })
      .catch(() => undefined);
    return () => {
      gone = true;
    };
  }, [credentials, mayRead]);

  return names;
}

/** Who an id is, by name when known. */
export function nameOf(names: ReadonlyMap<string, string>, id: string): string {
  return names.get(id) ?? id;
}
