/** Whether a call's room is open to be joined, said by the call's own log: `room.opened`, or the call ending first. */

import { useEffect, useState } from "react";

import { doorUrl } from "./api";
import { useCredentials } from "./credentials";
import { openLog } from "./stream";

/** `waiting`: the call has no room yet; `open`: `room.opened` was written; `over`: the call ended first. */
export type RoomOpen = "waiting" | "open" | "over";

const ROOM_OPENED = "room.opened";
const CALL_ENDED = "call.ended";

/** Follow one call's log for the entry that says its room is there. */
export function useRoomOpen(call: string): RoomOpen {
  const credentials = useCredentials();
  const [room, setRoom] = useState<RoomOpen>("waiting");

  useEffect(() => {
    setRoom("waiting");
    // Either entry decides it, and the stream is closed then. The stream's own markers
    // (`log.caught_up`, `log.gap`) come whatever types are asked for, and decide nothing.
    const close = openLog(doorUrl(credentials, `/v1/calls/${call}/events`, { types: `${ROOM_OPENED},${CALL_ENDED}` }), credentials, {
      onEntry(entry) {
        if (entry.type !== ROOM_OPENED && entry.type !== CALL_ENDED) return;
        setRoom(entry.type === ROOM_OPENED ? "open" : "over");
        close();
      },
      onPaint: () => undefined,
      // A sealed call's stream answers 204 with nothing more to say: its room never opens.
      onConnection: (now) => now === "ended" && setRoom((was) => (was === "open" ? was : "over")),
      onRefused: () => undefined,
    });
    return close;
  }, [call, credentials]);

  return room;
}
