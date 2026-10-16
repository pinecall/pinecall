// useRoom makes one room for a mounted component, reads the options it rendered last, and closes the room on unmount.

import { act, createElement, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import type { RoomOptions } from "../../src/index.js";
import { useRoom, type RoomHandle } from "../../src/react/index.js";
import { settle } from "../a-fake-gateway.js";
import { aRoom, LOG, MINTED } from "../a-room-at-hand.js";

Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);

/** A component that hands every render's handle to the test. */
function mounted(options: () => RoomOptions, strict = false): { handles: RoomHandle[]; rerender: () => void; unmount: () => void } {
  const handles: RoomHandle[] = [];
  const Visitor = (): null => {
    handles.push(useRoom(options()));
    return null;
  };
  const root = createRoot(document.createElement("div"));
  const tree = (): ReturnType<typeof createElement> =>
    strict ? createElement(StrictMode, null, createElement(Visitor)) : createElement(Visitor);
  act(() => root.render(tree()));
  return {
    handles,
    rerender: () => act(() => root.render(tree())),
    unmount: () => act(() => root.unmount()),
  };
}

/** The options a page would write inline: new objects, new functions, every render. */
function inline(fakes: ReturnType<typeof aRoom>, said: string[], label: () => string): () => RoomOptions {
  return () => ({
    tokens: async (scope) => {
      said.push(`${label()} ${scope}`);
      return MINTED;
    },
    log: (call) => `/api/log?call=${call}`,
    fetch: fakes.gateway.fetch,
    livekit: fakes.livekit.load,
  });
}

describe("useRoom", () => {
  it("keeps one room across renders, and runs the options it rendered last", async () => {
    const fakes = aRoom();
    fakes.gateway.answer(LOG, { stream: [], then: "hold" });
    const said: string[] = [];
    let render = "first";
    const { handles, rerender, unmount } = mounted(inline(fakes, said, () => render));
    render = "second";
    rerender();

    expect(handles.at(-1)?.start).toBe(handles[0]?.start);
    await act(async () => {
      await handles.at(-1)?.start("chat");
    });
    expect(said).toEqual(["second chat"]);
    expect(handles.at(-1)?.phase).toBe("live");

    unmount();
    await settle();
    expect(fakes.gateway.requests[0]?.aborted).toBe(true);
    expect(fakes.livekit.room.connected).toBe(false);
  });

  it("hands StrictMode's second mount a room that is open", async () => {
    const fakes = aRoom();
    fakes.gateway.answer(LOG, { stream: [], then: "hold" });
    const said: string[] = [];
    const { handles, unmount } = mounted(inline(fakes, said, () => "strict"), true);
    await act(async () => {
      await handles.at(-1)?.start("talk");
    });

    expect(said).toEqual(["strict talk"]);
    expect(handles.at(-1)?.phase).toBe("live");
    unmount();
  });
});
