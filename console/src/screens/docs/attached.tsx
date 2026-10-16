/** The bases this agent reads in the current world, from its settings: null until read, or what refused. */

import { type DocsConfig } from "@pinecall/core/wire/defs";
import { type TuningAnswer } from "@pinecall/core/wire/rest-org";
import { useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { WORLD } from "../../lib/mode";
import { readSettings } from "../settings/door";

/** Bases from production's settings, or from yours falling back to the team's. */
function basesRead(answer: TuningAnswer): DocsConfig[] {
  const row = WORLD === "production" ? answer.production : (answer.yours ?? answer.team);
  return row?.config.bases ?? [];
}

/** The base's name to how this agent reads it; read-only, the bases are edited in Configure. */
export function useAttached(agent: string): { read: Map<string, DocsConfig> | null; refused: string | null } {
  const credentials = useCredentials();
  const [bases, setBases] = useState<DocsConfig[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readSettings(credentials, agent).then(
      (answer) => {
        if (!gone) setBases(basesRead(answer));
      },
      (failed: unknown) => {
        if (!gone) setRefused(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  return { read: bases === null ? null : new Map(bases.map((one) => [one.base, one])), refused };
}
