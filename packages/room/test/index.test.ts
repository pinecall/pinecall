// The three public surfaces, pinned by name: adding an export means editing a list here on purpose.

import { describe, expect, it } from "vitest";

import * as page from "../src/index.js";
import * as react from "../src/react/index.js";
import * as server from "../src/server/index.js";

describe("the public surfaces", () => {
  it("@pinecall/room is the room, the rows, the screen and the karaoke", () => {
    expect(Object.keys(page).sort()).toEqual([
      "TASK_GIVE", "brief", "hosted", "joined", "knownBy", "litAt", "room", "rowsOf", "sayingOf", "screenOf", "soundedBy",
    ]);
  });

  it("@pinecall/room/react is three hooks and the screen", () => {
    expect(Object.keys(react).sort()).toEqual(["Screen", "useKaraoke", "useRoom", "useStore"]);
  });

  it("@pinecall/room/server is the three calls a key makes, and the refusal", () => {
    expect(Object.keys(server).sort()).toEqual(["GatewayRefused", "dial", "expect", "mint"]);
  });
});
