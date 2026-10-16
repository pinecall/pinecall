/** A follow and a fold wired the way the room wires them, with everything they said written down. */

import { LogFold } from "../src/log/fold.js";
import { followLog, type Ending } from "../src/log/follow.js";
import type { FakeGateway } from "./a-fake-gateway.js";

export interface Followed {
  fold: LogFold;
  connections: string[];
  endings: Ending[];
  skipped: string[];
  stop: () => void;
}

export function follow(gateway: FakeGateway, url: string): Followed {
  const skipped: string[] = [];
  const connections: string[] = [];
  const endings: Ending[] = [];
  const fold = new LogFold((why) => skipped.push(why));
  const stop = followLog(
    url,
    {
      onMessage: (message) => fold.take(message),
      onConnection: (connection) => connections.push(connection),
      onEnded: (ending) => endings.push(ending),
    },
    gateway.fetch,
  );
  return { fold, connections, endings, skipped, stop };
}
