/** Hook for the visibility the agent declared for each state field. */

import { useEffect, useState } from "react";
import { z } from "zod";

import { read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";

// Mirrors the runtime's types/agent.py.
const VISIBILITIES = ["public", "tenant", "pii"] as const;

/** Visibility of a state field; undeclared fields are `tenant`. */
export type Visibility = (typeof VISIBILITIES)[number];

// Only `state_fields` is read from GET /v1/agents/{slug}/config.
const DeclarationSchema = z.object({
  state_fields: z.record(z.string(), z.enum(VISIBILITIES)).default({}),
});

export function useDeclaredState(agent: string): Record<string, Visibility> {
  const credentials = useCredentials();
  const [declared, setDeclared] = useState<Record<string, Visibility>>({});

  useEffect(() => {
    let stopped = false;
    if (agent === "") {
      return;
    }
    void (async () => {
      try {
        const said = DeclarationSchema.parse(await read(credentials, `/v1/agents/${agent}/config`));
        if (!stopped) {
          setDeclared(said.state_fields);
        }
      } catch {
        // Unreadable config: every field falls back to the runtime default (`tenant`).
        if (!stopped) {
          setDeclared({});
        }
      }
    })();
    return () => {
      stopped = true;
    };
  }, [agent, credentials]);

  return declared;
}
