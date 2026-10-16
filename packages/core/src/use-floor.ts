/** Org-wide call list, read again whenever /v1/events says a call changed. */

import { type SessionLine, SessionListSchema } from "./wire/rest.js";
import { useState } from "react";

import { GatewayError, read, saidBy } from "./api";
import { useCredentials } from "./credentials";
import { useFed } from "./use-fed";
import type { Connection } from "./stream";

// The feed says every change to a row (a call ringing, starting, ending, sealed, judged, a person
// asked for), so the list is read when it speaks; `useFed` polls only while it is down.
/** Newest calls to read; older ones are paged via `calls-search.ts`. */
export const FLOOR_ROWS = 50;

/** Org calls newest first, stream status and last error. */
export interface Floor {
  lines: SessionLine[];
  connection: Connection;
  /** Incremented on agent.registered/detached, so the agent list can refetch. */
  agentsChanged: number;
  error: string | null;
  /** HTTP status of the last refusal (403: key lacks `calls`), or null. */
  refusedWith: number | null;
}

/** Error message and, for gateway errors, the HTTP status. */
export function refusal(refused: unknown): { error: string; refusedWith: number | null } {
  return { error: saidBy(refused), refusedWith: refused instanceof GatewayError ? refused.status : null };
}

/** Follow the org's calls. */
export function useFloor(limit = FLOOR_ROWS): Floor {
  const credentials = useCredentials();
  const [lines, setLines] = useState<SessionLine[]>([]);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [agentsChanged, setAgentsChanged] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [refusedWith, setRefusedWith] = useState<number | null>(null);

  useFed(
    () => {
      void (async (): Promise<void> => {
        try {
          const listed = SessionListSchema.parse(await read(credentials, "/v1/sessions", { limit }));
          setLines(listed.calls);
          setError(null);
          setRefusedWith(null);
        } catch (refused) {
          const said = refusal(refused);
          setError(said.error);
          setRefusedWith(said.refusedWith);
        }
      })();
    },
    {
      // /v1/events has no backlog or seq: a frame only triggers a refetch.
      onEntry(entry) {
        if (entry.type === "agent.registered" || entry.type === "agent.detached") {
          setAgentsChanged((count) => count + 1);
        }
      },
      onConnection: setConnection,
      onRefused: setError,
    },
    [limit],
  );

  return { lines, connection, agentsChanged, error, refusedWith };
}
