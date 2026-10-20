/** One of the insights' doors, read when a call seals and the feed says so: undefined while asked, null where the box does not have it. */

import { useState } from "react";

import { GatewayError, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useFed } from "@pinecall/core/use-fed";
import { type Asked, WHAT_MOVES_THE_NUMBERS } from "./insights";

/** `parse` reads what the door answered, and refuses a shape it does not know. */
export function useInsightDoor<T>(path: string, parse: (answered: unknown) => T, { day, days = 7, agent }: Asked = {}, extra: Record<string, number> = {}): T | null | undefined {
  const credentials = useCredentials();
  const [answer, setAnswer] = useState<T | null | undefined>(undefined);

  useFed(
    () => {
      const params = { days, ...(day === undefined ? {} : { day }), ...(agent === undefined ? {} : { agent }), ...extra };
      read(credentials, path, params).then(
        (answered) => setAnswer(parse(answered)),
        (refused: unknown) => {
          // A box older than this door answers 404, a key without `calls` 403: either way, nothing to draw.
          if (refused instanceof GatewayError && [403, 404].includes(refused.status)) setAnswer(null);
        },
      );
    },
    { types: WHAT_MOVES_THE_NUMBERS },
    [path, day, days, agent, ...Object.values(extra)],
  );

  return answer;
}
