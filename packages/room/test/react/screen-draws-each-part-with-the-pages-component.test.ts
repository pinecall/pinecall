// <Screen> draws each part the agent named with the page's component of that name, and says which it has none for.

import { act, createElement, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { Screen } from "../../src/react/index.js";

Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);

const Stage = ({ desk, children }: { desk: string; children?: ReactNode }): ReactNode => createElement("section", { "data-desk": desk }, children);
const Slot = ({ time }: { time: string }): ReactNode => createElement("button", null, time);

describe("<Screen>", () => {
  it("gives each part its props and what it holds, and skips a part the page does not know", () => {
    const unknown: string[] = [];
    const screen = [
      {
        part: "stage",
        props: { desk: "front" },
        children: [{ part: "slot", props: { time: "09:30" }, children: [] }, "or", { part: "map", props: {}, children: [] }],
      },
    ];
    const host = document.createElement("div");
    const root = createRoot(host);
    act(() => root.render(createElement(Screen, { screen, parts: { stage: Stage, slot: Slot }, onUnknown: (part) => unknown.push(part) })));

    expect(host.innerHTML).toBe('<section data-desk="front"><button>09:30</button>or</section>');
    expect(unknown).toEqual(["map"]);
    act(() => root.unmount());
  });
});
