// useStore reads any store of this package the way React reads an external store: on every change, and no longer once unmounted.

import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { useStore } from "../../src/react/index.js";
import { cell } from "../../src/store.js";

Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);

describe("useStore", () => {
  it("renders the store's state, again on every change, and stops hearing it once unmounted", () => {
    const store = cell({ phase: "idle" });
    const rendered: string[] = [];
    const Phase = (): null => {
      rendered.push(useStore(store).phase);
      return null;
    };
    const root = createRoot(document.createElement("div"));
    act(() => root.render(createElement(Phase)));
    act(() => store.publish({ phase: "live" }));
    act(() => root.unmount());
    store.publish({ phase: "ended" });

    expect(rendered).toEqual(["idle", "live"]);
  });
});
