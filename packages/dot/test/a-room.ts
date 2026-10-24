/** A room as a page makes one, that never opens: its idle state is all a face or a tutor reads before a call. */

import { room, type RoomStore } from "@pinecall/room";

export function aRoom(): RoomStore {
  return room({
    tokens: async () => {
      throw new Error("a test asks for no tokens");
    },
  });
}
